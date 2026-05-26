from __future__ import annotations

import json
from pathlib import Path

from .context import GeneratedProject
from .holes import Hole, ScanResult
from .paths import get_project_bindings_python_dir, get_project_py_impl_dir, get_project_supercode_dir


def emit_python_project(scan: ScanResult, payloads: dict[str, str], workdir: Path, project_root: Path) -> GeneratedProject:
    actual_workdir = get_project_supercode_dir(project_root)
    py_impl_dir = get_project_py_impl_dir(project_root)
    bindings_dir = get_project_bindings_python_dir(project_root)
    py_impl_dir.mkdir(parents=True, exist_ok=True)
    bindings_dir.mkdir(parents=True, exist_ok=True)

    impl_files: list[Path] = []
    entries: list[dict] = []
    for hole in scan.holes:
        if hole.kind != "local_func":
            raise ValueError(f"unsupported Python hole kind: {hole.kind}")
        impl_path = py_impl_dir / f"{scan.source_file.stem}.{hole.enclosing_function}.{hole.line}.{hole.hole_hash}.py"
        hole.impl_path = str(impl_path)
        impl_path.write_text(payloads[hole.hole_hash], encoding="utf-8")
        impl_files.append(impl_path)
        entries.append(
            {
                "source_file": str(hole.source_file.resolve()),
                "line": hole.line,
                "enclosing_function": hole.enclosing_function,
                "generated_symbol": hole.generated_symbol,
                "impl_path": str(impl_path.resolve()),
                "kind": hole.kind,
            }
        )

    registry_path = actual_workdir / "python_registry.json"
    registry_path.write_text(json.dumps({"entries": entries}, indent=2, sort_keys=True), encoding="utf-8")

    return GeneratedProject(
        scan=scan,
        project_root=project_root,
        source_header=None,
        impl_files=impl_files,
        manifest_path=actual_workdir / "manifest.json",
        generation_backend="unknown",
        python_registry=registry_path,
    )
