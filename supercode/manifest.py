from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .context import ResolvedHole


def save_manifest(path: Path, resolved_holes: list[ResolvedHole]) -> Path:
    payload = {
        "version": 1,
        "holes": [
            {
                "id": item.id,
                "kind": item.hole.kind,
                "source_file": str(item.hole.source_file),
                "line": item.hole.line,
                "column": item.hole.column,
                "enclosing_function": item.hole.enclosing_function,
                "public_name": item.public_name,
                "language": item.hole.language,
                "signature": item.signature,
                "source_hash": item.hole.source_hash,
                "hole_hash": item.hole.hole_hash,
                "impl": {
                    "kind": item.impl.kind,
                    "language": item.impl.language,
                    "path": item.impl.path,
                    "symbol": item.impl.symbol,
                    "hash": item.impl.hash,
                    "backend": item.impl.backend,
                    "provider": item.impl.provider,
                    "model": item.impl.model,
                    "library": item.impl.library,
                    "header": item.impl.header,
                },
                "artifacts": item.artifacts,
                "typed_params": [asdict(param) for param in item.hole.typed_params],
                "args": item.hole.args,
                "return_type": item.hole.return_type,
            }
            for item in resolved_holes
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "version" not in data:
        legacy_generation = data.get("generation", {})
        holes = []
        for item in data.get("holes", []):
            holes.append(
                {
                    "id": item.get("exported_name")
                    or item.get("type_name")
                    or (
                        f"{Path(item.get('source_file', '')).name}:{item.get('enclosing_function')}:{item.get('line')}"
                        if item.get("kind") == "local_func"
                        else item.get("generated_symbol")
                    ),
                    "kind": item.get("kind"),
                    "source_file": item.get("source_file"),
                    "line": item.get("line"),
                    "column": item.get("column"),
                    "enclosing_function": item.get("enclosing_function"),
                    "public_name": item.get("exported_name") or item.get("type_name"),
                    "language": "python" if str(item.get("source_file", "")).endswith(".py") else "c",
                    "signature": item.get("generated_symbol"),
                    "source_hash": item.get("source_hash"),
                    "hole_hash": item.get("hole_hash"),
                    "impl": {
                        "kind": "generated" if item.get("impl_path") else "missing",
                        "language": "python" if str(item.get("impl_path", "")).endswith(".py") else "c",
                        "path": item.get("impl_path"),
                        "symbol": item.get("generated_symbol"),
                        "hash": None,
                        "backend": legacy_generation.get("backend", "unknown"),
                        "provider": legacy_generation.get("provider"),
                        "model": legacy_generation.get("model"),
                        "library": None,
                        "header": None,
                    },
                    "artifacts": {},
                }
            )
        return {"version": 1, "holes": holes}
    return data
