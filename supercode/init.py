from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .config import DEFAULT_CONFIG
from .holes import Hole
from .paths import (
    get_packaged_include_dir,
    get_project_bindings_python_dir,
    get_project_generated_include_dir,
    get_project_impl_dir,
    get_project_py_impl_dir,
    get_project_supercode_dir,
    get_runtime_package_path,
)
from .scanner import scan_file

SCAN_SUFFIXES = {".c", ".cpp", ".cc", ".cxx", ".py"}
IGNORED_DIRS = {".git", ".supercode", "build", "dist", "__pycache__"}


@dataclass(slots=True)
class InitResult:
    config_status: str
    clangd_status: str
    pyright_status: str
    ide_header_status: str
    warnings: list[str]


def _discover_source_files(root: Path) -> list[Path]:
    found: set[Path] = set()
    explicit_files = [root.glob("*.c"), root.glob("*.cpp"), root.glob("*.cc"), root.glob("*.cxx")]
    for iterator in explicit_files:
        for path in iterator:
            if path.is_file():
                found.add(path)

    for base in ("examples", "src"):
        base_path = root / base
        if not base_path.exists():
            continue
        for path in base_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SCAN_SUFFIXES:
                continue
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            found.add(path)
    return sorted(found)


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _render_c_signature(return_type: str, typed_params: list) -> str:
    if not typed_params:
        return "void"
    return ", ".join(f"{param.type_text} {param.name}" for param in typed_params)


def _render_ide_header(holes: list[Hole]) -> str:
    guard = "SUPERCODE_IDE_H"
    export_lines: list[str] = []
    struct_lines: list[str] = []
    class_lines: list[str] = []

    for hole in holes:
        if hole.kind in {"export_func", "import_func"} and (hole.exported_name or hole.imported_name) and hole.return_type:
            name = hole.exported_name or hole.imported_name
            export_lines.append(
                f"{hole.return_type} {name}({_render_c_signature(hole.return_type, hole.typed_params)});"
            )
        elif hole.kind == "struct" and hole.type_name:
            name = hole.type_name
            struct_lines.extend(
                [
                    f"typedef struct {name} {name};",
                    f"{name} *{name}_create(void);",
                    f"void {name}_destroy({name} *v);",
                    f"void {name}_push({name} *v, int x);",
                    f"int {name}_get(const {name} *v, int index);",
                    f"int {name}_size(const {name} *v);",
                    "",
                ]
            )
        elif hole.kind == "class" and hole.type_name:
            name = hole.type_name
            class_lines.extend(
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

    export_lines = _unique_ordered(export_lines)
    if export_lines:
        export_lines.append("")

    content: list[str] = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "#define SUPERCODE_RESOLVED 1",
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
        *export_lines,
        *struct_lines,
        "#ifdef __cplusplus",
        "}",
        "#endif",
        "",
        "#ifdef __cplusplus",
        *class_lines,
        "#endif",
        "",
        f"#endif /* {guard} */",
        "",
    ]
    return "\n".join(content)


def _render_clangd(cwd: Path) -> str:
    include_dir = get_packaged_include_dir().resolve()
    supercode_include_dir = get_project_generated_include_dir(cwd).resolve()
    ide_header = (supercode_include_dir / "supercode_ide.h").resolve()
    return "\n".join(
        [
            "CompileFlags:",
            "  Add:",
            f"    - -I{include_dir}",
            f"    - -I{supercode_include_dir}",
            "    - -DSUPERCODE_IDE=1",
            "    - -include",
            f"    - {ide_header}",
            "",
        ]
    )


def _render_pyrightconfig() -> str:
    payload = {
        "include": ["examples", "src", "."],
        "extraPaths": [
            ".",
            ".supercode/bindings/python",
            ".supercode/py_impl",
            str(get_runtime_package_path().resolve()),
        ],
        "reportMissingImports": True,
    }
    return json.dumps(payload, indent=2) + "\n"


def init_project(cwd: Path | None = None, force: bool = False) -> InitResult:
    cwd = cwd or Path.cwd()
    config_path = cwd / "supercode.toml"
    clangd_path = cwd / ".clangd"
    pyright_path = cwd / "pyrightconfig.json"
    workdir = get_project_supercode_dir(cwd)
    include_dir = get_project_generated_include_dir(cwd)
    impl_dir = get_project_impl_dir(cwd)
    py_impl_dir = get_project_py_impl_dir(cwd)
    cache_dir = workdir / "cache"
    bindings_dir = get_project_bindings_python_dir(cwd).parent
    ide_header_path = include_dir / "supercode_ide.h"

    warnings: list[str] = []

    if config_path.exists() and not force:
        config_status = "supercode.toml already exists"
    else:
        config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
        config_status = "generated supercode.toml"

    workdir.mkdir(exist_ok=True)
    include_dir.mkdir(parents=True, exist_ok=True)
    impl_dir.mkdir(parents=True, exist_ok=True)
    py_impl_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    bindings_dir.mkdir(parents=True, exist_ok=True)

    if clangd_path.exists() and not force:
        clangd_status = ".clangd already exists. Use `super init --force` to overwrite."
    else:
        clangd_path.write_text(_render_clangd(cwd), encoding="utf-8")
        clangd_status = "generated .clangd"

    if pyright_path.exists() and not force:
        pyright_status = "pyrightconfig.json already exists. Use `super init --force` to overwrite."
    else:
        pyright_path.write_text(_render_pyrightconfig(), encoding="utf-8")
        pyright_status = "generated pyrightconfig.json"

    holes: list[Hole] = []
    for path in _discover_source_files(cwd):
        try:
            holes.extend(scan_file(path).holes)
        except Exception as exc:
            warnings.append(f"warning: failed to scan {path}: {exc}")

    ide_header_path.write_text(_render_ide_header(holes), encoding="utf-8")
    ide_header_status = "generated .supercode/include/supercode_ide.h"

    return InitResult(
        config_status=config_status,
        clangd_status=clangd_status,
        pyright_status=pyright_status,
        ide_header_status=ide_header_status,
        warnings=warnings,
    )
