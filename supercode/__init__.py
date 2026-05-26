from __future__ import annotations

__version__ = "0.1.0"

import importlib.util
import inspect
import json
import os
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "__version__",
    "super_func",
    "super_class",
    "super_export",
    "import_func",
    "load_registry",
    "is_runtime_ready",
]

_REGISTRY_CACHE: dict[str, Any] | None = None
_MODULE_CACHE: dict[str, Any] = {}
_RUNTIME_ERROR = "supercode.super_func was called without generated implementation. Run this file with `super`."


def load_registry(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None and path is None:
        return _REGISTRY_CACHE

    candidate = Path(path) if path is not None else None
    if candidate is None:
        env_path = os.getenv("SUPERCODE_REGISTRY")
        if env_path:
            candidate = Path(env_path)
        else:
            candidate = Path.cwd() / ".supercode" / "python_registry.json"
    if not candidate.exists():
        raise RuntimeError(_RUNTIME_ERROR)
    data = json.loads(candidate.read_text(encoding="utf-8"))
    if "entries" in data and "locals" not in data:
        data = {"locals": data.get("entries", []), "exports": {}}
    if path is None:
        _REGISTRY_CACHE = data
    return data


def is_runtime_ready() -> bool:
    try:
        load_registry()
    except RuntimeError:
        return False
    return True


def _load_module(module_path: str) -> Any:
    cached = _MODULE_CACHE.get(module_path)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(Path(module_path).stem, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load generated module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULE_CACHE[module_path] = module
    return module


def super_func(return_type: type, *args: Any) -> Any:
    try:
        registry = load_registry()
    except RuntimeError as exc:
        raise RuntimeError(_RUNTIME_ERROR) from exc

    frame = inspect.currentframe()
    caller = frame.f_back if frame is not None else None
    if caller is None:
        raise RuntimeError(_RUNTIME_ERROR)
    filename = str(Path(caller.f_code.co_filename).resolve())
    function_name = caller.f_code.co_name
    line = caller.f_lineno

    for entry in registry.get("locals", []):
        if (
            entry.get("source_file") == filename
            and entry.get("enclosing_function") == function_name
            and entry.get("line") == line
        ):
            module = _load_module(entry["impl_path"])
            helper = getattr(module, entry["generated_symbol"])
            return helper(*args)
    raise RuntimeError(_RUNTIME_ERROR)


def import_func(name: str, returns: type | None = None, args: list[type] | None = None) -> Callable[..., Any]:
    registry = load_registry()
    export = registry.get("exports", {}).get(name)
    if export is None:
        raise RuntimeError(f"SuperCode import resolution failed: export `{name}` was not found.")
    if export.get("kind") == "c_export":
        module = _load_module(export["module_path"])
        return getattr(module, export["callable"])
    if export.get("kind") == "python_export":
        module = _load_module(export["module_path"])
        return getattr(module, export["callable"])
    raise RuntimeError(f"SuperCode import resolution failed: unsupported export backend for `{name}`.")


def super_export(func: Callable[..., Any]) -> Callable[..., Any]:
    setattr(func, "__supercode_export__", True)
    return func


def super_class(name: str, *args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("supercode.super_class runtime dispatch is not implemented in v0")
