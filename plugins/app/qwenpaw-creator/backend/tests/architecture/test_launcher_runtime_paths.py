from __future__ import annotations

from pathlib import Path


QWENPAW_ROOT = Path(__file__).resolve().parents[6]


def test_qwenpaw_launcher_provisions_an_external_creator_runtime_root() -> None:
    source = (QWENPAW_ROOT / "scripts" / "run_creator_app.sh").read_text(
        encoding="utf-8"
    )

    assert "CREATOR_DATA_ROOT:-$WORKING_DIR/creator-runtime" in source
    assert (
        "CREATOR_MODEL_CONFIG_PATH:-$CREATOR_DATA_ROOT/config/model_config.json"
        in source
    )
    assert "export CREATOR_DATA_ROOT" in source
    assert "export CREATOR_MODEL_CONFIG_PATH" in source
    assert "CREATOR_DIR/data/model_config.json" not in source
    assert '--exclude "__pycache__/"' in source
    assert '--exclude "*.pyc"' in source


def test_qwenpaw_launcher_installs_the_in_tree_creator_app() -> None:
    source = (QWENPAW_ROOT / "scripts" / "run_creator_app.sh").read_text(
        encoding="utf-8"
    )

    assert 'CREATOR_DIR="$ROOT_DIR/plugins/app/qwenpaw-creator"' in source
    assert 'find "$target_dir" -type d -name "__pycache__"' in source
    assert '-name "*.pyc" -o -name "*.pyo"' in source
    assert 'rsync "${rsync_args[@]}" "$CREATOR_DIR/" "$target_dir/"' in source
    assert '"$QWENPAW_BIN" plugin validate "$target_dir"' in source
    assert 'exec "$QWENPAW_BIN" app --host "$HOST" --port "$PORT"' in source
