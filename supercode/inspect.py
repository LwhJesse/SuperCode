from __future__ import annotations

from pathlib import Path

from .config import load_config
from .manifest import load_manifest
from .paths import get_project_root, get_project_supercode_dir


def inspect_workdir(show_source: bool = False) -> str:
    workdir = get_project_supercode_dir(get_project_root())
    manifest_path = workdir / "manifest.json"
    if not manifest_path.exists():
        return f"no manifest found at {manifest_path}"
    data = load_manifest(manifest_path)
    generation = data.get("generation", {})
    lines: list[str] = []
    lines.append(
        f"backend={generation.get('backend', '-')} "
        f"real_llm={generation.get('is_real_llm', False)} "
        f"provider={generation.get('provider') or '-'} "
        f"model={generation.get('model') or '-'}"
    )
    lines.append("")
    for item in data.get("holes", []):
        lines.append(
            f"{item['kind']}: {item['source_file']}:{item['line']} "
            f"enclosing={item.get('enclosing_function') or '-'} "
            f"symbol={item.get('generated_symbol') or '-'} "
            f"impl={item.get('impl_path') or '-'}"
        )
        impl_path = item.get("impl_path")
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
