# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for QwenPaw Desktop (Tauri sidecar).

Shared spec for both macOS and Windows. Builds an onedir backend bundle so the
desktop startup can load Python directly without onefile extraction. The same
bundle also includes a qwenpaw CLI executable for the Windows installer PATH
option.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

REPO_ROOT = Path(SPECPATH).parent.parent

SRC = REPO_ROOT / "src" / "qwenpaw"
if sys.platform == "darwin":
    codesign_identity = os.environ.get(
        "PYINSTALLER_CODESIGN_IDENTITY"
    ) or os.environ.get("APPLE_SIGNING_IDENTITY")
    if not codesign_identity:
        codesign_identity = None
else:
    codesign_identity = None


def collect_tree(source_dir, target_dir):
    return [
        (
            str(path),
            str(Path(target_dir) / path.relative_to(source_dir).parent),
        )
        for path in source_dir.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.relative_to(source_dir).parts
        and path.suffix not in {".pyc", ".pyo"}
    ]


def collect_selected_tree(source_root, target_root, relative_paths):
    collected = []
    for relative in relative_paths:
        source = source_root / relative
        target = Path(target_root) / relative
        if source.is_dir():
            collected += collect_tree(source, str(target))
        elif source.is_file():
            collected.append((str(source), str(target.parent)))
        else:
            raise SystemExit(f"required runtime path not found: {source}")
    return collected


# Match the legacy desktop package: the FastAPI backend serves the web console
# from qwenpaw/console, so Tauri can navigate to the backend-hosted same-origin
# console after the sidecar is ready.
CONSOLE_DIST = REPO_ROOT / "console" / "dist"
if not (CONSOLE_DIST / "index.html").is_file():
    raise SystemExit(
        f"console dist not found at {CONSOLE_DIST}; "
        "run npm run build:prod in console/ before PyInstaller"
    )

_data_dirs = [
    ("agents/skills", "qwenpaw/agents/skills"),
    ("agents/md_files", "qwenpaw/agents/md_files"),
    ("tokenizer", "qwenpaw/tokenizer"),
    ("security/tool_guard/rules", "qwenpaw/security/tool_guard/rules"),
    ("security/skill_scanner/rules", "qwenpaw/security/skill_scanner/rules"),
    ("security/skill_scanner/data", "qwenpaw/security/skill_scanner/data"),
    ("app/channels/yuanbao/proto", "qwenpaw/app/channels/yuanbao/proto"),
]
datas = [
    (str(SRC / src), dst) for src, dst in _data_dirs if (SRC / src).is_dir()
]
datas += collect_tree(CONSOLE_DIST, "qwenpaw/console")

CREATOR_SOURCE = REPO_ROOT / "plugins" / "app" / "qwenpaw-creator"
CREATOR_RUNTIME_PATHS = (
    "__init__.py",
    "plugin.py",
    "plugin.json",
    "requirements.txt",
    "backend/api/__init__.py",
    "backend/api/dependencies.py",
    "backend/api/file_asset_routes.py",
    "backend/api/file_command_routes.py",
    "backend/api/file_execution_routes.py",
    "backend/api/file_media_routes.py",
    "backend/api/file_session_routes.py",
    "backend/api/file_source_intelligence_routes.py",
    "backend/api/file_view_routes.py",
    "backend/api/model_routes.py",
    "backend/api/project_file_routes.py",
    "backend/api/project_routes.py",
    "backend/api/router.py",
    "backend/domain",
    "backend/models/__init__.py",
    "backend/models/asr_model.py",
    "backend/models/concurrency.py",
    "backend/models/config.py",
    "backend/models/dashscope_multimodal.py",
    "backend/models/image",
    "backend/models/media_transport.py",
    "backend/models/model_capability_cache.py",
    "backend/models/native_content.py",
    "backend/models/vlm_model.py",
    "backend/models/video_model.py",
    "backend/schemas",
    "backend/services/__init__.py",
    "backend/services/file_agent_runtime",
    "backend/services/media_files",
    "backend/services/project_files",
    "backend/services/runtime_files",
    "backend/services/specialist_tools.py",
    "backend/services/source_analysis",
    "backend/services/storage_root.py",
    "backend/utils/__init__.py",
    "backend/utils/env.py",
    "backend/utils/exceptions.py",
    "backend/utils/logger.py",
    "backend/utils/paths.py",
    "backend/utils/remote_download.py",
    "backend/utils/retry.py",
    "ui/dist",
)
datas += collect_selected_tree(
    CREATOR_SOURCE,
    "qwenpaw/_bundled_plugins/app/qwenpaw-creator",
    CREATOR_RUNTIME_PATHS,
)

# Include reme package data files (configs, tool yamls, etc.)
datas += collect_data_files("reme")
datas += collect_data_files("whisper")
datas += collect_data_files("agentscope")
datas += collect_data_files(
    "agentscope.tool._builtin._scripts",
    include_py_files=True,
)
datas += collect_data_files(
    "agentscope.workspace._mcp_gateway",
    include_py_files=True,
)

# Collect package metadata for packages that use importlib.metadata at runtime.
# Keep this allowlist in sync when adding runtime dependencies that query
# importlib.metadata, otherwise packaged sidecars may fail only after install.
_metadata_pkgs = [
    "qwenpaw",
    "fastmcp",
    "mcp",
    "httpx",
    "httpcore",
    "anyio",
    "sniffio",
    "starlette",
    "pydantic",
    "pydantic-core",
    "pydantic-settings",
    "uvicorn",
    "openai",
    "anthropic",
    "tiktoken",
    "agentscope",
    "agentscope-runtime",
    "huggingface_hub",
    "modelscope",
    "openai-whisper",
]
for _pkg in _metadata_pkgs:
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

a = Analysis(
    [
        str(SRC / "tauri" / "entry.py"),
        str(SRC / "tauri" / "cli_entry.py"),
    ],
    pathex=[str(REPO_ROOT), str(REPO_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # uvicorn internals (not auto-discovered by PyInstaller)
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # All CLI sub-commands (dynamically loaded by Click)
        *collect_submodules("qwenpaw.cli"),
        # All channel adapters (imported on-demand at runtime)
        *collect_submodules("qwenpaw.app.channels"),
        # ACP runner support is lazily imported by delegate_external_agent.
        *collect_submodules("qwenpaw.agents.acp"),
        # ASGI app entry points
        "qwenpaw.app._app",
        "qwenpaw.app.multi_agent_manager",
        "qwenpaw.app.chats",
        "qwenpaw.app.task_tracker",
        "qwenpaw.runtime.commands",
        # Backup modules are exposed through qwenpaw.backup.__getattr__, which
        # PyInstaller cannot discover from static imports.
        *collect_submodules("qwenpaw.backup"),
        # Third-party packages that use dynamic imports. Use
        # collect_submodules() for packages that load many submodules by name;
        # keep the bare package string when runtime code imports only the
        # package root or when PyInstaller needs the top-level module anchor.
        *collect_submodules("dotenv"),
        "dotenv",
        *collect_submodules("acp"),
        "acp",
        "psutil",
        "multipart",
        "websockets",
        "modelscope",
        "modelscope.hub.api",
        "modelscope.hub.snapshot_download",
        *collect_submodules("agentscope.tool._builtin._scripts"),
        *collect_submodules("agentscope.workspace._mcp_gateway"),
        *collect_submodules("whisper"),
        *collect_submodules("chromadb"),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)


def script_entry(file_name):
    for item in a.scripts:
        if Path(item[1]).name == file_name:
            return [item]
    raise SystemExit(f"script entry not found: {file_name}")


backend_exe = EXE(
    pyz,
    script_entry("entry.py"),
    [],
    name="qwenpaw-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX triggers antivirus false positives and can corrupt binaries.
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=codesign_identity,
    exclude_binaries=True,
)

cli_exe = EXE(
    pyz,
    script_entry("cli_entry.py"),
    [],
    name="qwenpaw",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=codesign_identity,
    exclude_binaries=True,
)

coll = COLLECT(
    backend_exe,
    cli_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="qwenpaw-backend",
)
