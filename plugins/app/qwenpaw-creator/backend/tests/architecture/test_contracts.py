from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path
import tomllib

from domain.enums import CreatorCommandType, SpecialistRole, TaskKind, UnitTaskType
from domain.refs import parse_target_ref, safe_relative_path, validate_workspace_ref


BACKEND = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = BACKEND.parent
REPOSITORY_ROOT = PLUGIN_ROOT.parent
QWENPAW_ROOT = PLUGIN_ROOT.parents[2]
UI_SOURCE = PLUGIN_ROOT / "ui" / "src"

_BACKEND_SOURCE_ROOTS = {
    "api",
    "domain",
    "migrations",
    "models",
    "schemas",
    "scripts",
    "services",
    "tests",
    "utils",
}
_BACKEND_ROOT_FILES = {
    "dev_main.py",
    "plugin_app.py",
}
_UI_SOURCE_ROOTS = {
    "api",
    "app",
    "components",
    "contracts",
    "hooks",
    "lib",
    "pages",
    "routing",
    "selectors",
    "store",
    "test",
}
_UI_ROOT_FILES = {"main.tsx", "vite-env.d.ts"}


def test_role_and_command_contracts_are_exact() -> None:
    assert len(SpecialistRole) == 7
    assert {role.value for role in SpecialistRole} == {
        "source_intelligence_agent",
        "story_planning_agent",
        "visual_development_agent",
        "unit_planning_routing_agent",
        "r2v_generation_director",
        "ai_editing_director",
        "review_consistency_agent",
    }
    assert len(CreatorCommandType) == 42
    assert {item.value for item in UnitTaskType} == {"r2v", "edit"}


def test_source_intelligence_has_no_retired_second_task_contract() -> None:
    retired = "source_" "understanding"
    assert retired not in {kind.value for kind in TaskKind}
    assert not (BACKEND / "services" / "media" / f"{retired}.py").exists()

    violations: list[str] = []
    for root in (BACKEND, UI_SOURCE):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            relative = path.relative_to(root)
            if "tests" in relative.parts or "migrations" in relative.parts or "__pycache__" in relative.parts:
                continue
            if retired in path.read_text(encoding="utf-8"):
                violations.append(str(path.relative_to(PLUGIN_ROOT)))
    assert violations == []


def test_reference_contracts_reject_aliases_and_path_escape() -> None:
    assert parse_target_ref("unit:u-1").identifier == "u-1"
    assert parse_target_ref("asset-import:task-1").kind == "asset-import"
    artifact = parse_target_ref("artifact:unit:u-1/storyboard")
    assert artifact.kind == "artifact"
    assert artifact.identifier == "unit:u-1/storyboard"
    assert validate_workspace_ref("artifact://unit-u-1-video@av-2")
    assert safe_relative_path("story/sections/001000--s/units/001000--u/title.txt")

    for bad in ("../secret", "/absolute", "story/../secret"):
        try:
            safe_relative_path(bad)
        except Exception:
            pass
        else:  # pragma: no cover - assertion branch
            raise AssertionError(f"path escape accepted: {bad}")

    for alias in ("t" + "2v", "i" + "2v", "task" + "_type", "workbench", "workflow"):
        assert alias not in {item.value for item in UnitTaskType}


def test_production_architecture_does_not_import_removed_runtime() -> None:
    forbidden = {
        "router",
        "services.creator_agent",
        "services.production_run",
        "services.agents",
        "services.workflow",
        "services.workspace.assembly",
        "services.workspace.runs",
        "services.workspace.patches",
    }
    violations: list[str] = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.relative_to(BACKEND).parts:
            continue
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == old or name.startswith(old + ".") for old in forbidden):
                    violations.append(f"{path.relative_to(BACKEND)} -> {name}")
    assert violations == []


def test_api_package_initializer_does_not_compose_the_http_router() -> None:
    """Only the two documented composition roots may import ``api.router``."""

    initializer = BACKEND / "api" / "__init__.py"
    tree = ast.parse(initializer.read_text(encoding="utf-8"), filename=str(initializer))
    imported_modules = {
        name
        for node in ast.walk(tree)
        for name in (
            [item.name for item in node.names]
            if isinstance(node, ast.Import)
            else [node.module]
            if isinstance(node, ast.ImportFrom) and node.module
            else []
        )
    }

    assert imported_modules.isdisjoint({"router", "api.router"})


def test_plugin_entrypoint_imports_only_the_file_native_runtime() -> None:
    """The distributable plugin must not pull the retired SQL driver into boot."""

    entrypoint = PLUGIN_ROOT / "plugin.py"
    tree = ast.parse(entrypoint.read_text(encoding="utf-8"), filename=str(entrypoint))
    imported_modules = {
        name
        for node in ast.walk(tree)
        for name in (
            [item.name for item in node.names]
            if isinstance(node, ast.Import)
            else [node.module]
            if isinstance(node, ast.ImportFrom) and node.module
            else []
        )
    }

    assert "services.project_files.facade" in imported_modules
    assert "services.file_agent_runtime.registry" in imported_modules
    assert "services.creator.loop" not in imported_modules
    assert "services.runtime.database" not in imported_modules
    assert "services.creator.runtime_driver" not in imported_modules


def test_creator_declares_only_dependencies_missing_from_qwenpaw() -> None:
    def requirements(path: Path) -> set[str]:
        return {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

    plugin_dependencies = set(
        json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))[
            "dependencies"
        ]
    )
    root_requirements = requirements(PLUGIN_ROOT / "requirements.txt")
    qwenpaw_project = tomllib.loads(
        (QWENPAW_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]

    def package_name(requirement: str) -> str:
        name = re.split(r"[<>=!~;\[]", requirement, maxsplit=1)[0]
        return re.sub(r"[-_.]+", "-", name.strip()).casefold()

    qwenpaw_packages = {
        package_name(requirement)
        for requirement in (
            list(qwenpaw_project.get("dependencies", []))
            + [
                item
                for group in qwenpaw_project.get("optional-dependencies", {}).values()
                for item in group
            ]
        )
    }
    creator_packages = {package_name(item) for item in root_requirements}

    assert plugin_dependencies == root_requirements
    assert creator_packages == {
        "oss2",
        "imageio-ffmpeg",
    }
    assert creator_packages.isdisjoint(qwenpaw_packages)
    assert not (BACKEND / "requirements.txt").exists()
    assert not (BACKEND / "pyproject.toml").exists()


def test_final_source_files_stay_inside_the_documented_roots() -> None:
    backend_violations: list[str] = []
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND)
        if "__pycache__" in relative.parts:
            continue
        if len(relative.parts) == 1:
            if relative.as_posix() not in _BACKEND_ROOT_FILES:
                backend_violations.append(relative.as_posix())
        elif relative.parts[0] not in _BACKEND_SOURCE_ROOTS:
            backend_violations.append(relative.as_posix())

    ui_violations: list[str] = []
    for path in UI_SOURCE.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        relative = path.relative_to(UI_SOURCE)
        if len(relative.parts) == 1:
            if relative.as_posix() not in _UI_ROOT_FILES:
                ui_violations.append(relative.as_posix())
        elif relative.parts[0] not in _UI_SOURCE_ROOTS:
            ui_violations.append(relative.as_posix())

    assert backend_violations == []
    assert ui_violations == []


def test_removed_paths_construction_files_and_runtime_outputs_are_absent() -> None:
    forbidden = (
        BACKEND / "agents",
        BACKEND / "services" / "agents",
        BACKEND / "services" / "workflow",
        BACKEND / "services" / "creator_agent.py",
        BACKEND / "services" / "production_run.py",
        BACKEND / "services" / "media" / ("source_" "understanding.py"),
        BACKEND / "router.py",
        BACKEND / "pipeline",
        BACKEND / "generated",
        PLUGIN_ROOT / "generated",
        PLUGIN_ROOT / "data",
        PLUGIN_ROOT / "ui" / "src" / "compat",
        PLUGIN_ROOT / "ui" / "src" / "components" / "canvas",
        PLUGIN_ROOT / "ui" / "src" / "components" / "agent" / "ProposalPanel.tsx",
        PLUGIN_ROOT / "ui" / "src" / "components" / "agent" / "AgentDiffText.tsx",
        PLUGIN_ROOT / "ui" / "src" / "types" / "index.ts",
        PLUGIN_ROOT / "file-disposition.tsv",
        PLUGIN_ROOT / "scripts" / "refactor",
    )
    assert [str(path.relative_to(PLUGIN_ROOT)) for path in forbidden if path.exists()] == []

    # ``run.sh`` deliberately creates this package output locally before
    # installing the plugin.  It must remain an ignored runtime artifact, not
    # a tracked source-tree deliverable.
    tracked_ui_dist = subprocess.run(
        ["git", "ls-files", "--", "qwenpaw-creator/ui/dist"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert tracked_ui_dist == []


def test_cutover_module_owners_have_no_old_path_aliases() -> None:
    expected = (
        "api/dependencies.py",
        "api/project_routes.py",
        "api/project_file_routes.py",
        "api/file_asset_routes.py",
        "api/file_command_routes.py",
        "api/file_media_routes.py",
        "api/file_session_routes.py",
        "api/file_execution_routes.py",
        "api/file_view_routes.py",
        "api/model_routes.py",
        "services/storage_root.py",
        "services/project_files/store.py",
        "services/project_files/commit.py",
        "services/project_files/recovery.py",
        "services/project_files/review.py",
        "services/runtime_files/session_store.py",
        "services/runtime_files/execution_store.py",
        "services/runtime_files/idempotency_store.py",
    )
    removed = (
        "alembic.ini",
        "api/asset_routes.py",
        "api/command_routes.py",
        "api/creator_session_routes.py",
        "api/media_routes.py",
        "api/observability_routes.py",
        "api/review_routes.py",
        "api/specialist_run_routes.py",
        "api/task_routes.py",
        "api/view_routes.py",
        "services/runtime/database.py",
        "services/runtime/schema.py",
    )

    assert [path for path in expected if not (BACKEND / path).is_file()] == []
    assert [path for path in removed if (BACKEND / path).exists()] == []
    assert list((BACKEND / "migrations").rglob("*.py")) == []
    assert list((BACKEND / "services" / "runtime").rglob("*.py")) == []


def test_backend_has_no_forbidden_business_tokens_and_ui_has_no_retired_authorities() -> None:
    second = re.compile(
        r"taskType[^\n]*(?:t2v|i2v)|['\"]task_type['\"]"
        r"|['\"]/agent/|['\"]/api/ai/|PUT /projects"
    )
    retired_backend_authorities = re.compile(
        r"legacy_creator|creator_main_agent|workflow_dag"
        r"|['\"]/agent/|['\"]/api/ai/|PUT /projects",
        re.IGNORECASE,
    )
    backend_violations: list[str] = []
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND)
        if "tests" in relative.parts or "__pycache__" in relative.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if retired_backend_authorities.search(text):
            backend_violations.append(str(path.relative_to(PLUGIN_ROOT)))

    retired_ui_imports = re.compile(
        r"@/store/(?:projectStore|proposalStore|agentStore|reviewStore|taskStore)"
        r"|@/lib/backendApi|@/lib/agentApi|components/canvas|useCanvasHistory"
    )
    ui_authority_violations: list[str] = []
    ui_token_violations: list[str] = []
    for path in UI_SOURCE.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        if retired_ui_imports.search(text):
            ui_authority_violations.append(str(path.relative_to(PLUGIN_ROOT)))
        if second.search(text) or re.search(
            r"^['\"]use client['\"];?", text, re.MULTILINE
        ):
            ui_token_violations.append(str(path.relative_to(PLUGIN_ROOT)))

    assert backend_violations == []
    assert ui_authority_violations == []
    assert ui_token_violations == []
