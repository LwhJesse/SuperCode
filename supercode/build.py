from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from .bindings_python import maybe_build_export_library
from .config import Config
from .context import BuildProject
from .paths import (
    get_packaged_include_dir,
    get_project_bindings_python_dir,
    get_project_generated_include_dir,
    get_project_py_impl_dir,
    get_project_supercode_dir,
    get_runtime_package_path,
)


def _compile_language(path: Path, scan_language: str) -> str:
    if path.suffix == ".py":
        return "python"
    if path.suffix in {".cpp", ".cc", ".cxx"}:
        return "cpp"
    if path.suffix == ".c":
        return "c"
    return scan_language


def _compiler_for(language: str, config: Config) -> str:
    if language == "cpp":
        return config.build.cxx
    return config.build.cc


def _phase_print(message: str, quiet: bool) -> None:
    if not quiet:
        print(message)


def build_source(project: BuildProject, config: Config, output: Path, *, quiet: bool = False, verbose: bool = False) -> None:
    if project.scan.language == "python":
        raise RuntimeError("build_source does not handle Python projects")
    project_root = project.project_root.resolve()
    packaged_include_dir = get_packaged_include_dir().resolve()
    generated_include_dir = get_project_generated_include_dir(project_root).resolve()
    cache_dir = get_project_supercode_dir(project_root) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    object_files: list[Path] = []
    sources = [project.scan.source_file, *project.impl_files]
    for source in sources:
        language = _compile_language(Path(source), project.scan.language)
        compiler = _compiler_for(language, config)
        obj_path = cache_dir / f"{Path(source).name}.o"
        cmd = [
            compiler,
            "-c",
            str(source),
            f"-I{packaged_include_dir}",
            f"-I{generated_include_dir}",
            "-o",
            str(obj_path),
        ]
        if source == project.scan.source_file and project.source_header is not None:
            cmd.extend(["-include", str(project.source_header)])
        if verbose:
            _phase_print(f"[build] {shlex.join(cmd)}", quiet)
        subprocess.run(cmd, check=True)
        object_files.append(obj_path)

    link_compiler = _compiler_for(project.scan.language, config)
    link_cmd = [link_compiler, *[str(path) for path in object_files], "-o", str(output)]
    if verbose:
        _phase_print(f"[link] {shlex.join(link_cmd)}", quiet)
    subprocess.run(link_cmd, check=True)

    export_holes = [item.hole for item in project.resolved_holes if item.hole.kind == "export_func"]
    if project.export_library:
        maybe_build_export_library(config, export_holes, project.impl_files, project.export_library)


def build_generated_only(project: BuildProject, config: Config) -> None:
    export_holes = [item.hole for item in project.resolved_holes if item.hole.kind == "export_func"]
    if project.export_library:
        maybe_build_export_library(config, export_holes, project.impl_files, project.export_library)


def render_compile_command(project: BuildProject, config: Config, output: Path) -> str:
    if project.scan.language == "python":
        return shlex.join([sys.executable, str(project.scan.source_file)])
    compiler = _compiler_for(project.scan.language, config)
    project_root = project.project_root.resolve()
    packaged_include_dir = get_packaged_include_dir().resolve()
    generated_include_dir = get_project_generated_include_dir(project_root).resolve()
    cmd = [
        compiler,
        str(project.scan.source_file),
        *[str(path) for path in project.impl_files],
        f"-I{packaged_include_dir}",
        f"-I{generated_include_dir}",
        "-include",
        str(project.source_header),
        "-o",
        str(output),
    ]
    return shlex.join(cmd)


def passthrough_command(source_file: Path, output: Path | None = None, config: Config | None = None) -> list[str]:
    if source_file.suffix == ".c":
        if output is None:
            raise ValueError("C passthrough requires -o/--output")
        return [config.build.cc if config else "gcc", str(source_file), "-o", str(output)]
    if source_file.suffix in {".cpp", ".cc", ".cxx"}:
        if output is None:
            raise ValueError("C++ passthrough requires -o/--output")
        return [config.build.cxx if config else "g++", str(source_file), "-o", str(output)]
    if source_file.suffix == ".py":
        return [sys.executable, str(source_file)]
    raise ValueError(f"unsupported source file: {source_file}")


def run_passthrough(source_file: Path, output: Path | None = None, *, config: Config | None = None) -> list[str]:
    cmd = passthrough_command(source_file, output, config=config)
    if source_file.suffix == ".py":
        env = os.environ.copy()
        parts = [str(get_runtime_package_path().resolve()), str(Path.cwd().resolve())]
        existing = env.get("PYTHONPATH")
        if existing:
            parts.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(parts)
        subprocess.run(cmd, check=True, env=env)
    else:
        subprocess.run(cmd, check=True)
    return cmd


def run_python_project(project: BuildProject, config: Config) -> None:
    if project.python_registry is None:
        raise RuntimeError("missing python registry for Python project")
    env = os.environ.copy()
    env["SUPERCODE_REGISTRY"] = str(project.python_registry.resolve())
    env["SUPERCODE_PROJECT_ROOT"] = str(project.project_root.resolve())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    project_root = project.project_root.resolve()
    parts = [
        str(get_runtime_package_path().resolve()),
        str(project_root),
        str(get_project_bindings_python_dir(project_root).resolve()),
        str(get_project_py_impl_dir(project_root).resolve()),
    ]
    existing = env.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    subprocess.run([config.build.python, str(project.scan.source_file)], check=True, env=env)
