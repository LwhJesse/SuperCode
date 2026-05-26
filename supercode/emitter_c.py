from __future__ import annotations

from pathlib import Path

from .bindings_python import emit_python_binding, maybe_build_export_library
from .context import GeneratedProject
from .holes import Hole, ScanResult
from .paths import get_project_supercode_dir


def _param_decl(hole: Hole) -> str:
    if not hole.typed_params:
        return "void"
    return ", ".join(f"{param.type_text} {param.name}".replace(" * ", " *").replace(" & ", " &") for param in hole.typed_params)


def _macro_arg_list(hole: Hole) -> str:
    return ", ".join(param.name for param in hole.typed_params)


def _prototype(hole: Hole) -> str:
    if hole.kind in {"local_func", "export_func"}:
        return f"{hole.return_type} {hole.generated_symbol}({_param_decl(hole)});"
    if hole.kind == "struct":
        name = hole.type_name
        return "\n".join(
            [
                f"typedef struct {name} {name};",
                f"{name} *{name}_create(void);",
                f"void {name}_destroy({name} *v);",
                f"void {name}_push({name} *v, int x);",
                f"int {name}_get(const {name} *v, int index);",
                f"int {name}_size(const {name} *v);",
            ]
        )
    raise ValueError(f"unsupported C hole kind: {hole.kind}")


def _build_source_header(scan: ScanResult) -> str:
    guard = f"SUPERCODE_GENERATED_{scan.source_file.stem.upper()}_SC_H"
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "#define SUPERCODE_RESOLVED 1",
        "",
    ]
    local_holes = [hole for hole in scan.holes if hole.kind == "local_func"]
    struct_holes = [hole for hole in scan.holes if hole.kind == "struct"]
    if local_holes:
        lines.extend(
            [
                "#define __SC_SUPER_CONCAT2(a, b) a##b",
                "#define __SC_SUPER_CONCAT(a, b) __SC_SUPER_CONCAT2(a, b)",
                "#ifndef super_func",
                "#define super_func(return_type, ...) __SC_SUPER_CONCAT(__SC_SUPER_FUNC_AT_LINE_, __LINE__)(__VA_ARGS__)",
                "#endif",
                "",
            ]
        )
        for hole in local_holes:
            params = _macro_arg_list(hole)
            invocation = params
            lines.append(f"#define __SC_SUPER_FUNC_AT_LINE_{hole.line}({params}) {hole.generated_symbol}({invocation})")
        lines.append("")
    if struct_holes:
        lines.extend(
            [
                "#ifndef super_struct",
                "#define super_struct(name)",
                "#endif",
                "",
            ]
        )
        for hole in struct_holes:
            lines.append(_prototype(hole))
            lines.append("")
    for hole in scan.holes:
        if hole.kind == "local_func":
            lines.append(_prototype(hole))
            lines.append("")
    lines.extend([f"#endif /* {guard} */", ""])
    return "\n".join(lines)


def emit_c_project(scan: ScanResult, payloads: dict[str, str], workdir: Path, project_root: Path) -> GeneratedProject:
    actual_workdir = get_project_supercode_dir(project_root)
    include_dir = actual_workdir / "include"
    impl_dir = actual_workdir / "impl"
    abi_dir = actual_workdir / "abi"
    bindings_dir = actual_workdir / "bindings" / "python"
    include_dir.mkdir(parents=True, exist_ok=True)
    impl_dir.mkdir(parents=True, exist_ok=True)
    abi_dir.mkdir(parents=True, exist_ok=True)
    bindings_dir.mkdir(parents=True, exist_ok=True)

    source_header = include_dir / f"{scan.source_file.stem}.sc.h"
    source_header.write_text(_build_source_header(scan), encoding="utf-8")

    impl_files: list[Path] = []
    export_holes: list[Hole] = []
    for hole in scan.holes:
        if hole.kind == "local_func":
            impl_name = f"{scan.source_file.stem}.{hole.enclosing_function}.{hole.line}.{hole.hole_hash}.c"
        elif hole.kind == "export_func":
            impl_name = f"{hole.exported_name}.c"
            export_holes.append(hole)
        elif hole.kind == "struct":
            impl_name = f"{hole.type_name}.c"
        else:
            raise ValueError(f"unsupported C hole kind: {hole.kind}")
        impl_path = impl_dir / impl_name
        hole.impl_path = str(impl_path)
        impl_path.write_text(payloads[hole.hole_hash], encoding="utf-8")
        impl_files.append(impl_path)

    export_header = None
    export_library = None
    python_binding = None
    if export_holes:
        export_header = include_dir / "supercode_exports.h"
        export_header.write_text(
            "\n".join([_prototype(hole) for hole in export_holes]) + "\n",
            encoding="utf-8",
        )
        export_library = abi_dir / "libsupercode_generated.so"
        python_binding = bindings_dir / "supercode_generated.py"
        emit_python_binding(export_holes, python_binding, export_library)

    return GeneratedProject(
        scan=scan,
        project_root=project_root,
        source_header=source_header,
        impl_files=impl_files,
        manifest_path=actual_workdir / "manifest.json",
        generation_backend="unknown",
        export_header=export_header,
        export_library=export_library,
        python_binding=python_binding,
    )
