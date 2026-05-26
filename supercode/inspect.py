from __future__ import annotations

from pathlib import Path

from .manifest import load_manifest
from .paths import get_project_supercode_dir


def inspect_workdir(project_root: Path | None = None, show_source: bool = False) -> str:
    root = (project_root or Path.cwd()).resolve()
    manifest_path = get_project_supercode_dir(root) / "manifest.json"
    if not manifest_path.exists():
        return f"no manifest found at {manifest_path}"
    data = load_manifest(manifest_path)
    lines: list[str] = []
    for item in data.get("holes", []):
        impl = item.get("impl", {})
        lines.append(
            f"{item['kind']}: {item['source_file']}:{item['line']} "
            f"enclosing={item.get('enclosing_function') or '-'} "
            f"symbol={impl.get('symbol') or '-'} "
            f"impl={impl.get('path') or '-'} "
            f"backend={impl.get('backend') or '-'} "
            f"provider={impl.get('provider') or '-'} "
            f"model={impl.get('model') or '-'}"
        )
        impl_path = impl.get("path")
        if impl_path and Path(impl_path).exists():
            lines.append(Path(impl_path).read_text(encoding="utf-8").rstrip())
        if show_source:
            source_path = Path(item["source_file"])
            if source_path.exists():
                source_lines = source_path.read_text(encoding="utf-8").splitlines()
                index = item["line"] - 1
                if 0 <= index < len(source_lines):
                    lines.append(f"SOURCE: {source_lines[index]}")
        lines.append("")
    return "\n".join(lines).strip()
