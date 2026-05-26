from __future__ import annotations

import hashlib
from pathlib import Path

from .config import Config, ImplementationConfig
from .context import ImplementationRef, ResolvedHole
from .holes import Hole, ScanResult
from .manifest import load_manifest
from .paths import get_project_supercode_dir


def file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def hole_id(hole: Hole) -> str:
    if hole.kind == "local_func":
        return f"{hole.source_file.name}:{hole.enclosing_function}:{hole.line}"
    if hole.kind in {"export_func", "import_func", "python_export_func"}:
        return hole.exported_name or hole.imported_name or hole.generated_symbol or hole.hole_hash
    if hole.kind in {"struct", "class"}:
        return hole.type_name or hole.generated_symbol or hole.hole_hash
    return hole.hole_hash


def hole_public_name(hole: Hole) -> str | None:
    return hole.exported_name or hole.imported_name or hole.type_name


def hole_signature(hole: Hole) -> str:
    params = ", ".join(f"{param.type_text} {param.name}" for param in hole.typed_params) or "void"
    if hole.kind == "local_func":
        args = ", ".join(hole.args)
        return f"super_func({hole.return_type}, {args})"
    if hole.kind == "export_func":
        return f"{hole.return_type} {hole.exported_name}({params})"
    if hole.kind == "import_func":
        return f"{hole.return_type} {hole.imported_name}({params})"
    if hole.kind == "struct":
        return f"super_struct({hole.type_name})"
    if hole.kind == "class":
        return f"super_class({hole.type_name})"
    if hole.kind == "python_export_func":
        return f"{hole.exported_name}({params}) -> {hole.return_type}"
    return hole.hole_hash


def _handwritten_for_hole(config: Config, hole: Hole) -> ImplementationConfig | None:
    for key in [hole_id(hole), hole.exported_name, hole.type_name]:
        if key and key in config.implementations:
            return config.implementations[key]
    return None


def _manifest_entry_by_id(manifest_data: dict, id_text: str) -> dict | None:
    for item in manifest_data.get("holes", []):
        if item.get("id") == id_text:
            return item
    return None


def _generated_impl_from_manifest(entry: dict, hole: Hole) -> ImplementationRef | None:
    impl = entry.get("impl") or {}
    if impl.get("kind") != "generated":
        return None
    if entry.get("hole_hash") != hole.hole_hash:
        return None
    path_text = impl.get("path")
    if not path_text:
        return None
    path = Path(path_text)
    if not path.exists():
        return None
    actual_hash = file_sha256(path)
    if impl.get("hash") != actual_hash:
        return None
    return ImplementationRef(
        kind="generated",
        language=impl.get("language", hole.language),
        path=str(path),
        symbol=impl.get("symbol"),
        hash=actual_hash,
        backend="reused_generated",
        provider=impl.get("provider"),
        model=impl.get("model"),
    )


def _resolve_export_target(
    name: str,
    config: Config,
    manifest_data: dict,
) -> ImplementationRef | None:
    impl_cfg = config.implementations.get(name)
    if impl_cfg and impl_cfg.source:
        source_path = (config.project_root or Path.cwd()) / impl_cfg.source
        if source_path.exists():
            return ImplementationRef(
                kind="handwritten",
                language=impl_cfg.language,
                path=str(source_path.resolve()),
                symbol=impl_cfg.symbol or name,
                hash=file_sha256(source_path),
                backend="handwritten",
                header=impl_cfg.header,
                library=impl_cfg.library,
            )
    entry = _manifest_entry_by_id(manifest_data, name)
    if entry is None:
        return None
    impl = _generated_impl_from_manifest(entry, Hole(  # type: ignore[arg-type]
        kind="export_func",
        language=entry.get("language", "c"),
        source_file=Path(entry.get("source_file", ".")),
        line=int(entry.get("line", 0)),
        column=int(entry.get("column", 0)),
        intent="",
        source_hash=entry.get("source_hash", ""),
        hole_hash=entry.get("hole_hash", ""),
        exported_name=name,
    ))
    return impl


def resolve_scan(scan: ScanResult, config: Config) -> list[ResolvedHole]:
    manifest_path = get_project_supercode_dir(config.project_root or Path.cwd()) / "manifest.json"
    manifest_data = load_manifest(manifest_path) if manifest_path.exists() else {"holes": []}
    resolved: list[ResolvedHole] = []
    for hole in scan.holes:
        current_id = hole_id(hole)
        public_name = hole_public_name(hole)
        signature = hole_signature(hole)
        impl_cfg = _handwritten_for_hole(config, hole)
        if hole.kind == "import_func":
            target = _resolve_export_target(hole.imported_name or "", config, manifest_data)
            impl = target or ImplementationRef(kind="missing", language=hole.language, backend="missing")
        elif impl_cfg and impl_cfg.source:
            source_path = (config.project_root or Path.cwd()) / impl_cfg.source
            if source_path.exists():
                impl = ImplementationRef(
                    kind="handwritten",
                    language=impl_cfg.language,
                    path=str(source_path.resolve()),
                    symbol=impl_cfg.symbol or hole.generated_symbol,
                    hash=file_sha256(source_path),
                    backend="handwritten",
                    library=impl_cfg.library,
                    header=impl_cfg.header,
                )
            else:
                impl = ImplementationRef(kind="missing", language=hole.language, backend="missing")
        else:
            entry = _manifest_entry_by_id(manifest_data, current_id)
            impl = _generated_impl_from_manifest(entry, hole) if entry else None
            if impl is None:
                impl = ImplementationRef(kind="missing", language=hole.language, backend="missing")
        resolved.append(
            ResolvedHole(
                hole=hole,
                id=current_id,
                public_name=public_name,
                signature=signature,
                impl=impl,
            )
        )
    return resolved


def missing_resolutions(resolved_holes: list[ResolvedHole]) -> list[ResolvedHole]:
    return [item for item in resolved_holes if item.hole.kind != "import_func" and item.impl.kind == "missing"]


def missing_imports(resolved_holes: list[ResolvedHole]) -> list[ResolvedHole]:
    return [item for item in resolved_holes if item.hole.kind == "import_func" and item.impl.kind == "missing"]


def stale_resolutions(resolved_holes: list[ResolvedHole]) -> list[ResolvedHole]:
    stale: list[ResolvedHole] = []
    for item in resolved_holes:
        if item.impl.path and item.impl.hash:
            path = Path(item.impl.path)
            if not path.exists() or file_sha256(path) != item.impl.hash:
                stale.append(item)
    return stale
