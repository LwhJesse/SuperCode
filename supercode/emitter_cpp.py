from __future__ import annotations

from pathlib import Path

from .config import Config
from .context import GeneratedProject
from .holes import Hole, ScanResult
from .paths import get_project_supercode_dir


def _build_source_header(scan: ScanResult) -> str:
    guard = f"SUPERCODE_GENERATED_{scan.source_file.stem.upper()}_SC_HPP"
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "#define SUPERCODE_RESOLVED 1",
        "",
    ]
    class_holes = [hole for hole in scan.holes if hole.kind == "class"]
    if class_holes:
        lines.extend(
            [
                "#ifndef super_class",
                "#define super_class(name)",
                "#endif",
                "",
            ]
        )
    for hole in class_holes:
        name = hole.type_name
        lines.extend(
            [
                f"class {name} {{",
                "public:",
                f"    explicit {name}(int capacity);",
                f"    ~{name}();",
                "    void put(int key, double value);",
                "    double get(int key) const;",
                "    bool contains(int key) const;",
                "private:",
                "    struct Impl;",
                "    Impl* impl_;",
                "};",
                "",
            ]
        )
    lines.extend([f"#endif /* {guard} */", ""])
    return "\n".join(lines)


def emit_cpp_project(
    scan: ScanResult,
    payloads: dict[str, str],
    workdir: Path,
    config: Config,
    project_root: Path,
) -> GeneratedProject:
    actual_workdir = get_project_supercode_dir(project_root)
    include_dir = actual_workdir / "include"
    impl_dir = actual_workdir / "impl"
    include_dir.mkdir(parents=True, exist_ok=True)
    impl_dir.mkdir(parents=True, exist_ok=True)

    source_header = include_dir / f"{scan.source_file.stem}.sc.hpp"
    source_header.write_text(_build_source_header(scan), encoding="utf-8")

    impl_files: list[Path] = []
    for hole in scan.holes:
        if hole.kind != "class":
            raise ValueError(f"unsupported C++ hole kind: {hole.kind}")
        impl_path = impl_dir / f"{hole.type_name}.cpp"
        hole.impl_path = str(impl_path)
        impl_path.write_text(
            f'#include "{source_header.name}"\n\n{payloads[hole.hole_hash]}',
            encoding="utf-8",
        )
        impl_files.append(impl_path)

    return GeneratedProject(
        scan=scan,
        project_root=project_root,
        source_header=source_header,
        impl_files=impl_files,
        manifest_path=actual_workdir / "manifest.json",
        generation_backend="unknown",
    )
