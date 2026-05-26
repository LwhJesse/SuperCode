from __future__ import annotations

import json
from pathlib import Path

from .bindings_python import emit_python_binding
from .config import Config
from .context import BuildProject, ResolvedHole
from .holes import Hole, ScanResult
from .paths import (
    get_project_bindings_python_dir,
    get_project_generated_include_dir,
    get_project_impl_dir,
    get_project_py_impl_dir,
    get_project_supercode_dir,
)
from .resolver import file_sha256


def _param_decl(hole: Hole) -> str:
    if not hole.typed_params:
        return "void"
    return ", ".join(f"{param.type_text} {param.name}" for param in hole.typed_params)


def _macro_arg_list(hole: Hole) -> str:
    return ", ".join(param.name for param in hole.typed_params)


def _c_prototype(hole: Hole) -> str:
    name = hole.exported_name or hole.imported_name or hole.generated_symbol
    return f"{hole.return_type} {name}({_param_decl(hole)});"


def _struct_api(hole: Hole) -> str:
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


def _build_c_header(scan: ScanResult, resolved_holes: list[ResolvedHole]) -> str:
    guard = f"SUPERCODE_GENERATED_{scan.source_file.stem.upper()}_SC_H"
    lines = [f"#ifndef {guard}", f"#define {guard}", "#define SUPERCODE_RESOLVED 1", ""]
    local_holes = [item.hole for item in resolved_holes if item.hole.kind == "local_func"]
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
            lines.append(f"#define __SC_SUPER_FUNC_AT_LINE_{hole.line}({params}) {hole.generated_symbol}({params})")
        lines.append("")
    for item in resolved_holes:
        hole = item.hole
        if hole.kind == "local_func":
            lines.append(f"{hole.return_type} {hole.generated_symbol}({_param_decl(hole)});")
        elif hole.kind in {"export_func", "import_func"}:
            lines.append(_c_prototype(hole))
        elif hole.kind == "struct":
            lines.append(_struct_api(hole))
        if hole.kind in {"local_func", "export_func", "import_func", "struct"}:
            lines.append("")
    lines.extend([f"#endif /* {guard} */", ""])
    return "\n".join(lines)


def _build_cpp_header(scan: ScanResult, resolved_holes: list[ResolvedHole]) -> str:
    guard = f"SUPERCODE_GENERATED_{scan.source_file.stem.upper()}_SC_HPP"
    lines = [f"#ifndef {guard}", f"#define {guard}", "#define SUPERCODE_RESOLVED 1", ""]
    for item in resolved_holes:
        hole = item.hole
        if hole.kind == "class" and hole.type_name:
            name = hole.type_name
            lines.extend(
                [
                    "#ifndef super_class",
                    "#define super_class(name)",
                    "#endif",
                    "",
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
        elif hole.kind == "import_func":
            lines.extend(
                [
                    "#ifdef __cplusplus",
                    'extern "C" {',
                    "#endif",
                    _c_prototype(hole),
                    "#ifdef __cplusplus",
                    "}",
                    "#endif",
                    "",
                ]
            )
    lines.extend([f"#endif /* {guard} */", ""])
    return "\n".join(lines)


def prepare_project_dirs(project_root: Path) -> None:
    workdir = get_project_supercode_dir(project_root)
    get_project_generated_include_dir(project_root).mkdir(parents=True, exist_ok=True)
    get_project_impl_dir(project_root).mkdir(parents=True, exist_ok=True)
    get_project_py_impl_dir(project_root).mkdir(parents=True, exist_ok=True)
    get_project_bindings_python_dir(project_root).mkdir(parents=True, exist_ok=True)
    (workdir / "abi").mkdir(parents=True, exist_ok=True)
    (workdir / "cache").mkdir(parents=True, exist_ok=True)


def write_generated_impls(
    project_root: Path,
    generated_payloads: dict[str, str],
    resolved_holes: list[ResolvedHole],
) -> None:
    impl_dir = get_project_impl_dir(project_root)
    py_impl_dir = get_project_py_impl_dir(project_root)
    for item in resolved_holes:
        if item.impl.kind != "generated":
            continue
        hole = item.hole
        code = generated_payloads[hole.hole_hash]
        if hole.language == "python":
            impl_path = py_impl_dir / f"{hole.source_file.stem}.{hole.enclosing_function}.{hole.line}.{hole.hole_hash}.py"
        elif hole.kind == "local_func":
            impl_path = impl_dir / f"{hole.source_file.stem}.{hole.enclosing_function}.{hole.line}.{hole.hole_hash}.c"
        elif hole.kind == "export_func":
            impl_path = impl_dir / f"{hole.exported_name}.c"
        elif hole.kind == "struct":
            impl_path = impl_dir / f"{hole.type_name}.c"
        elif hole.kind == "class":
            impl_path = impl_dir / f"{hole.type_name}.cpp"
            code = f'#include "{hole.source_file.stem}.sc.hpp"\n\n{code}'
        else:
            continue
        impl_path.write_text(code, encoding="utf-8")
        item.impl.path = str(impl_path.resolve())
        item.impl.hash = file_sha256(impl_path)
        item.impl.symbol = hole.generated_symbol
        hole.impl_path = item.impl.path


def assemble_build_project(
    scan: ScanResult,
    config: Config,
    resolved_holes: list[ResolvedHole],
) -> BuildProject:
    project_root = (config.project_root or scan.source_file.parent).resolve()
    prepare_project_dirs(project_root)
    include_dir = get_project_generated_include_dir(project_root)
    source_header: Path | None
    if scan.language == "c":
        source_header = include_dir / f"{scan.source_file.stem}.sc.h"
        source_header.write_text(_build_c_header(scan, resolved_holes), encoding="utf-8")
    elif scan.language == "cpp":
        source_header = include_dir / f"{scan.source_file.stem}.sc.hpp"
        source_header.write_text(_build_cpp_header(scan, resolved_holes), encoding="utf-8")
    else:
        source_header = None

    impl_files: list[Path] = []
    export_holes: list[Hole] = []
    export_resolved: list[ResolvedHole] = []
    for item in resolved_holes:
        hole = item.hole
        if item.impl.path:
            impl_files.append(Path(item.impl.path))
        if hole.kind == "export_func" and item.impl.path:
            export_holes.append(hole)
            export_resolved.append(item)

    workdir = get_project_supercode_dir(project_root)
    binding_holes = list(export_holes)
    binding_impl_files = list(impl_files)
    if scan.language == "python":
        for item in resolved_holes:
            hole = item.hole
            if hole.kind == "import_func" and item.impl.path:
                binding_holes.append(
                    Hole(
                        kind="export_func",
                        language="c",
                        source_file=hole.source_file,
                        line=hole.line,
                        column=hole.column,
                        intent="",
                        source_hash=hole.source_hash,
                        hole_hash=hole.hole_hash,
                        return_type=hole.return_type or "int",
                        typed_params=hole.typed_params,
                        exported_name=hole.imported_name,
                        generated_symbol=hole.imported_name,
                    )
                )
                binding_impl_files.append(Path(item.impl.path))

    export_library = None
    python_binding = None
    python_registry = None
    if binding_holes:
        export_library = workdir / "abi" / "libsupercode_exports.so"
        python_binding = get_project_bindings_python_dir(project_root) / "supercode_generated.py"
        emit_python_binding(binding_holes, python_binding, export_library)
        for item in export_resolved:
            item.artifacts["binding"] = str(python_binding.resolve())
            item.artifacts["library"] = str(export_library.resolve())

    if scan.language == "python":
        entries = []
        exports = {}
        for item in resolved_holes:
            hole = item.hole
            if hole.kind == "local_func" and item.impl.path:
                entries.append(
                    {
                        "source_file": str(hole.source_file.resolve()),
                        "line": hole.line,
                        "enclosing_function": hole.enclosing_function,
                        "generated_symbol": hole.generated_symbol,
                        "impl_path": str(Path(item.impl.path).resolve()),
                    }
                )
            elif hole.kind == "import_func" and python_binding is not None:
                exports[hole.imported_name] = {
                    "kind": "c_export",
                    "module_path": str(python_binding.resolve()),
                    "callable": hole.imported_name,
                }
        for item in export_resolved:
            hole = item.hole
            if python_binding is not None:
                exports[hole.exported_name] = {
                    "kind": "c_export",
                    "module_path": str(python_binding.resolve()),
                    "callable": hole.exported_name,
                }
        python_registry = workdir / "python_registry.json"
        python_registry.write_text(json.dumps({"locals": entries, "exports": exports}, indent=2, sort_keys=True), encoding="utf-8")
        for item in resolved_holes:
            item.artifacts["registry"] = str(python_registry.resolve())

    for item in resolved_holes:
        if source_header is not None:
            item.artifacts["header"] = str(source_header.resolve())

    return BuildProject(
        scan=scan,
        project_root=project_root,
        source_header=source_header,
        impl_files=impl_files,
        manifest_path=workdir / "manifest.json",
        resolved_holes=resolved_holes,
        export_library=export_library,
        python_binding=python_binding,
        python_registry=python_registry,
    )
