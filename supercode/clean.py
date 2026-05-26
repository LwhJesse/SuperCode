from __future__ import annotations

import shutil
from pathlib import Path

from .config import load_config


def clean_workdir() -> Path:
    config = load_config()
    workdir = Path(config.supercode.workdir)
    if workdir.exists():
        shutil.rmtree(workdir)
    return workdir
