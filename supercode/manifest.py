from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .holes import Hole


def hole_to_manifest_record(hole: Hole) -> dict:
    return {
        "source_file": str(hole.source_file),
        "line": hole.line,
        "column": hole.column,
        "enclosing_function": hole.enclosing_function,
        "kind": hole.kind,
        "source_hash": hole.source_hash,
        "hole_hash": hole.hole_hash,
        "generated_symbol": hole.generated_symbol,
        "impl_path": hole.impl_path,
        "return_type": hole.return_type,
        "args": hole.args,
        "typed_params": [asdict(param) for param in hole.typed_params],
        "exported_name": hole.exported_name,
        "type_name": hole.type_name,
    }


def save_manifest(
    path: Path,
    holes: list[Hole],
    *,
    generation_backend: str,
    provider: str | None,
    model: str | None,
) -> Path:
    payload = {
        "generation": {
            "backend": generation_backend,
            "is_real_llm": generation_backend == "real_llm",
            "provider": provider,
            "model": model,
        },
        "holes": [hole_to_manifest_record(hole) for hole in holes],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
