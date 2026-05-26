from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .holes import Hole, ScanResult


@dataclass(slots=True)
class ImplementationRef:
    kind: str
    language: str
    path: str | None = None
    symbol: str | None = None
    hash: str | None = None
    backend: str = "missing"
    provider: str | None = None
    model: str | None = None
    library: str | None = None
    header: str | None = None


@dataclass(slots=True)
class ResolvedHole:
    hole: Hole
    id: str
    public_name: str | None
    signature: str
    impl: ImplementationRef
    artifacts: dict[str, str | None] = field(default_factory=dict)


@dataclass(slots=True)
class BuildProject:
    scan: ScanResult
    project_root: Path
    source_header: Path | None
    impl_files: list[Path]
    manifest_path: Path
    resolved_holes: list[ResolvedHole]
    export_library: Path | None = None
    python_binding: Path | None = None
    python_registry: Path | None = None
