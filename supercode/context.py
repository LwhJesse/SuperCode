from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .holes import Hole, ScanResult


@dataclass(slots=True)
class GeneratedUnit:
    hole: Hole
    header_path: Path | None
    impl_path: Path
    code: str


@dataclass(slots=True)
class GeneratedProject:
    scan: ScanResult
    project_root: Path
    source_header: Path | None
    impl_files: list[Path]
    manifest_path: Path
    generation_backend: str
    provider: str | None = None
    model: str | None = None
    export_header: Path | None = None
    export_library: Path | None = None
    python_binding: Path | None = None
    python_registry: Path | None = None
