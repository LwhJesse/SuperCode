from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

HoleKind = Literal["local_func", "export_func", "struct", "class"]
Language = Literal["c", "cpp", "python"]


@dataclass(slots=True)
class FunctionParam:
    type_text: str
    name: str


@dataclass(slots=True)
class FunctionContext:
    name: str
    return_type: str
    params: list[FunctionParam]
    start_line: int
    end_line: int


@dataclass(slots=True)
class Hole:
    kind: HoleKind
    language: Language
    source_file: Path
    line: int
    column: int
    intent: str
    source_hash: str
    hole_hash: str
    enclosing_function: str | None = None
    return_type: str | None = None
    args: list[str] = field(default_factory=list)
    typed_params: list[FunctionParam] = field(default_factory=list)
    exported_name: str | None = None
    type_name: str | None = None
    generated_symbol: str | None = None
    impl_path: str | None = None


@dataclass(slots=True)
class ScanResult:
    source_file: Path
    language: Language
    source_hash: str
    holes: list[Hole]
