from pathlib import Path

from supercode.config import init_config, load_config


def test_load_local_config(tmp_path: Path) -> None:
    path = tmp_path / "supercode.toml"
    path.write_text(
        "[build]\ncc = 'clang'\n\n[supercode]\nworkdir = '.cache-super'\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.build.cc == "clang"
    assert config.supercode.workdir == ".cache-super"


def test_init_config(tmp_path: Path) -> None:
    destination = tmp_path / "supercode.toml"
    init_config(destination)
    assert destination.exists()
