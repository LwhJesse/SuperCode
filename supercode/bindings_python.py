from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from .config import Config
from .holes import Hole


def emit_python_binding(export_holes: list[Hole], output_path: Path, library_path: Path) -> Path:
    lines = [
        "from __future__ import annotations",
        "",
        "import ctypes",
        "from pathlib import Path",
        "",
        f'_LIB = ctypes.CDLL(str(Path(__file__).resolve().parents[2] / "abi" / "{library_path.name}"))',
        "",
    ]
    for hole in export_holes:
        if hole.exported_name == "mode_min_tie":
            lines.extend(
                [
                    "_LIB.mode_min_tie.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]",
                    "_LIB.mode_min_tie.restype = ctypes.c_int",
                    "",
                    "def mode_min_tie(values: list[int]) -> int:",
                    "    array = (ctypes.c_int * len(values))(*values)",
                    "    return int(_LIB.mode_min_tie(array, len(values)))",
                    "",
                ]
            )
        else:
            argtypes = []
            for param in hole.typed_params:
                argtypes.append("ctypes.c_int")
            lines.extend(
                [
                    f"_LIB.{hole.exported_name}.argtypes = [{', '.join(argtypes)}]",
                    f"_LIB.{hole.exported_name}.restype = ctypes.c_int",
                    "",
                    f"def {hole.exported_name}(*args):",
                    f"    return _LIB.{hole.exported_name}(*args)",
                    "",
                ]
            )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def maybe_build_export_library(config: Config, export_holes: list[Hole], impl_files: list[Path], output_path: Path) -> Path:
    if not impl_files:
        return output_path
    cmd = [config.build.cc, "-shared", "-fPIC", *[str(path) for path in impl_files], "-o", str(output_path)]
    subprocess.run(cmd, check=True)
    return output_path
