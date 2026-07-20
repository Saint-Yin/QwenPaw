# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=use-implicit-booleaness-not-comparison
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap


BACKEND = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = BACKEND.parent
QWENPAW_ROOT = PLUGIN_ROOT.parents[2]

# Import roots and distribution names which would re-introduce a relational
# database, SQL ORM/query layer, or SQL driver into Creator.  Keep this list
# deliberately broader than the packages removed during the filesystem
# cutover: the invariant is "Creator is file-native", not merely "Creator no
# longer imports SQLAlchemy".
SQL_MODULES = {
    "MySQLdb",
    "adodbapi",
    "aiomysql",
    "aioodbc",
    "aiopg",
    "alembic",
    "aiosqlite",
    "apsw",
    "asyncmy",
    "asyncpg",
    "cx_Oracle",
    "databases",
    "dataset",
    "django",
    "duckdb",
    "ibm_db",
    "mariadb",
    "mysql",
    "mysqlclient",
    "oracledb",
    "ormar",
    "peewee",
    "pg8000",
    "piccolo",
    "pony",
    "psycopg",
    "psycopg2",
    "pymssql",
    "pymysql",
    "pyodbc",
    "pysqlite3",
    "pytds",
    "records",
    "sqlalchemy",
    "sqlmodel",
    "sqlite3",
    "tortoise",
}
LEGACY_ROUTE_MODULES = {
    "api.asset_routes",
    "api.command_routes",
    "api.creator_session_routes",
    "api.media_routes",
    "api.observability_routes",
    "api.review_routes",
    "api.specialist_run_routes",
    "api.task_routes",
    "api.view_routes",
}


def _requirement_name(requirement: str) -> str:
    """Normalize one PEP 508-ish dependency name for deny-list checks."""

    name = re.split(r"[<>=!~;\[]", requirement, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name.strip()).casefold()


def _sql_import_violations(paths: set[Path]) -> list[str]:
    violations: list[str] = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            elif (
                isinstance(node, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "__import__"
                ):
                    imported = [node.args[0].value]
                elif (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "importlib"
                    and node.func.attr == "import_module"
                ):
                    imported = [node.args[0].value]
            for module in imported:
                if module.split(".", 1)[0] in SQL_MODULES:
                    violations.append(
                        f"{path.relative_to(PLUGIN_ROOT)} -> {module}",
                    )
                if module == "services.runtime" or module.startswith(
                    "services.runtime.",
                ):
                    violations.append(
                        f"{path.relative_to(PLUGIN_ROOT)} -> legacy {module}",
                    )
    return violations


def _run_sql_blocked(
    script: str,
    *,
    data_root: Path,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["CREATOR_DATA_ROOT"] = str(data_root)
    environment["CREATOR_MODEL_CONFIG_PATH"] = str(
        data_root / "config" / "model_config.json",
    )
    environment["QWENPAW_WORKING_DIR"] = str(data_root.parent / "qwenpaw-home")
    environment["QWENPAW_SECRET_DIR"] = str(
        data_root.parent / "qwenpaw-secrets",
    )
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(QWENPAW_ROOT / "src"),
            str(PLUGIN_ROOT / "backend"),
            str(PLUGIN_ROOT),
        ),
    )
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=QWENPAW_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_import_and_startup_closure_is_sql_free(tmp_path: Path) -> None:
    result = _run_sql_blocked(
        f"""
        import asyncio
        import importlib.abc
        import json
        import sys

        blocked = {SQL_MODULES!r}
        legacy_routes = {LEGACY_ROUTE_MODULES!r}

        class SqlImportBlocker(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.', 1)[0] in blocked:
                    raise ImportError(f"blocked SQL module: {{fullname}}")
                return None

        sys.meta_path.insert(0, SqlImportBlocker())

        import api.router
        import dev_main
        import main
        from httpx import ASGITransport, AsyncClient

        assert legacy_routes.isdisjoint(sys.modules)
        assert "api.project_file_routes" in sys.modules
        assert "api.project_routes" in sys.modules
        assert "api.file_asset_routes" in sys.modules
        assert "api.file_command_routes" in sys.modules
        assert "api.file_session_routes" in sys.modules
        assert "api.file_source_intelligence_routes" in sys.modules
        assert "api.file_execution_routes" in sys.modules
        assert "api.file_media_routes" in sys.modules
        assert "api.file_view_routes" in sys.modules
        assert "api.model_routes" in sys.modules

        async def exercise_startup():
            await main._startup()
            assert main._file_services is not None
            assert main._file_services.startup_recovery.ok
            assert main._file_services.startup_review_recovery.ok
            await main._shutdown()

            async with dev_main.lifespan(dev_main.app):
                assert dev_main.creator_file_services(
                    dev_main.require_creator_data_root()
                ).startup_recovery.ok
                async with AsyncClient(
                    transport=ASGITransport(app=dev_main.app),
                    base_url="http://creator.test",
                ) as client:
                    response = await client.get("/api/qwenpaw-creator/health")
                assert response.status_code == 200
                payload = response.json()
                assert payload["status"] == "ok"
                assert payload["runtime"] == "creator-filesystem"
                assert payload["projectRecoveryErrors"] == 0
                assert payload["reviewRecoveryErrors"] == 0
                assert payload["dependencies"]["status"] == "ok"
                assert payload["dependencies"]["tools"]["jq"]["status"] == "ok"
                assert payload["dependencies"]["tools"]["ffmpeg"]["status"] == "ok"
                assert payload["dependencies"]["tools"]["ffprobe"]["status"] in {{
                    "ok",
                    "fallback",
                }}

        asyncio.run(exercise_startup())

        loaded_sql = sorted(
            name for name in sys.modules if name.split('.', 1)[0] in blocked
        )
        loaded_routes = sorted(
            name
            for name in sys.modules
            if name.startswith('api.') and name.endswith('_routes')
        )
        assert loaded_sql == []
        assert loaded_routes == [
            "api.file_asset_routes",
            "api.file_command_routes",
            "api.file_execution_routes",
            "api.file_media_routes",
            "api.file_session_routes",
            "api.file_source_intelligence_routes",
            "api.file_view_routes",
            "api.model_routes",
            "api.project_file_routes",
            "api.project_routes",
        ]
        print(json.dumps({{"sql": loaded_sql, "routes": loaded_routes}}))
        """,
        data_root=tmp_path / "creator-data",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {
        "sql": [],
        "routes": [
            "api.file_asset_routes",
            "api.file_command_routes",
            "api.file_execution_routes",
            "api.file_media_routes",
            "api.file_session_routes",
            "api.file_source_intelligence_routes",
            "api.file_view_routes",
            "api.model_routes",
            "api.project_file_routes",
            "api.project_routes",
        ],
    }
    assert not (tmp_path / "creator-data" / "creator.sqlite3").exists()


def test_distribution_metadata_declares_no_sql_packages() -> None:
    requirements = {
        line.strip()
        for line in (PLUGIN_ROOT / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    manifest = json.loads(
        (PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"),
    )

    normalized = {
        _requirement_name(requirement)
        for requirement in requirements | set(manifest["dependencies"])
    }
    assert {_requirement_name(name) for name in SQL_MODULES}.isdisjoint(
        normalized,
    )


def test_all_creator_executable_modules_are_sql_free() -> None:
    """Keep production code and executable support tooling off every SQL path."""

    python_files = {
        path
        for path in PLUGIN_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
        and not path.is_relative_to(BACKEND / "tests")
        and not path.is_relative_to(PLUGIN_ROOT / "e2e" / "tests")
    }
    assert python_files
    assert _sql_import_violations(python_files) == []
