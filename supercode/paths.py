from __future__ import annotations

from importlib import resources
from pathlib import Path


def get_package_dir() -> Path:
    return Path(__file__).resolve().parent


def get_runtime_package_path() -> Path:
    return get_package_dir().parent


def get_project_root(start: Path | None = None) -> Path:
    return (start or Path.cwd()).resolve()


def get_project_supercode_dir(project_root: Path) -> Path:
    return project_root / ".supercode"


def get_project_generated_include_dir(project_root: Path) -> Path:
    return get_project_supercode_dir(project_root) / "include"


def get_project_impl_dir(project_root: Path) -> Path:
    return get_project_supercode_dir(project_root) / "impl"


def get_project_bindings_python_dir(project_root: Path) -> Path:
    return get_project_supercode_dir(project_root) / "bindings" / "python"


def get_project_py_impl_dir(project_root: Path) -> Path:
    return get_project_supercode_dir(project_root) / "py_impl"


def get_packaged_include_dir() -> Path:
    package_candidate = get_package_dir() / "resources" / "include"
    if (package_candidate / "supercode.h").exists() and (package_candidate / "supercode.hpp").exists():
        return package_candidate

    resource_root = resources.files("supercode.resources").joinpath("include")
    with resources.as_file(resource_root) as resource_path:
        return Path(resource_path)
