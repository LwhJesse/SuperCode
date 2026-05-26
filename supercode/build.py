from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from .bindings_python import maybe_build_export_library
from .config import Config
from .context import GeneratedProject
from .paths import (
    get_packaged_include_dir,
    get_project_bindings_python_dir,
    get_project_generated_include_dir,
    get_project_py_impl_dir,
    get_runtime_package_path,
)


def build_source(project: GeneratedProject, config: Config, output: Path) -> None:
    if project.scan.language == "python":
        raise RuntimeError("build_source does not handle Python projects")
    compiler = config.build.cc if project.scan.language == "c" else config.build.cxx
    include_header = project.source_header
    if include_header is None:
        raise RuntimeError("missing generated header for compiled project")
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
        str(include_header),
        "-o",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    export_holes = [hole for hole in project.scan.holes if hole.kind == "export_func"]
    if project.export_library:
        maybe_build_export_library(config, export_holes, project.impl_files, project.export_library)


def build_generated_only(project: GeneratedProject, config: Config) -> None:
    export_holes = [hole for hole in project.scan.holes if hole.kind == "export_func"]
    if project.export_library:
        maybe_build_export_library(config, export_holes, project.impl_files, project.export_library)


def render_compile_command(project: GeneratedProject, config: Config, output: Path) -> str:
    if project.scan.language == "python":
        return shlex.join([sys.executable, str(project.scan.source_file)])
    compiler = config.build.cc if project.scan.language == "c" else config.build.cxx
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


def passthrough_command(source_file: Path, output: Path | None = None) -> list[str]:
    if source_file.suffix == ".c":
        if output is None:
            raise ValueError("C passthrough requires -o/--output")
        return ["gcc", str(source_file), "-o", str(output)]
    if source_file.suffix in {".cpp", ".cc", ".cxx"}:
        if output is None:
            raise ValueError("C++ passthrough requires -o/--output")
        return ["g++", str(source_file), "-o", str(output)]
    if source_file.suffix == ".py":
        return [sys.executable, str(source_file)]
    raise ValueError(f"unsupported source file: {source_file}")


def run_passthrough(source_file: Path, output: Path | None = None) -> list[str]:
    cmd = passthrough_command(source_file, output)
    if source_file.suffix == ".py":
        env = os.environ.copy()
        parts = [
            str(get_runtime_package_path().resolve()),
            str(Path.cwd().resolve()),
        ]
        existing = env.get("PYTHONPATH")
        if existing:
            parts.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(parts)
        subprocess.run(cmd, check=True, env=env)
    else:
        subprocess.run(cmd, check=True)
    return cmd


def run_python_project(project: GeneratedProject) -> None:
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
    subprocess.run([sys.executable, str(project.scan.source_file)], check=True, env=env)
