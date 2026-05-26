from __future__ import annotations

from pathlib import Path

from .config import load_config
from .manifest import load_manifest
from .resolver import file_sha256, missing_resolutions, resolve_scan, stale_resolutions
from .scanner import scan_file


def verify_project(source: str | Path | None = None) -> tuple[bool, str]:
    if source is not None:
        scan = scan_file(source)
        config = load_config(scan.source_file)
        resolved = resolve_scan(scan, config)
        missing = missing_resolutions(resolved)
        stale = stale_resolutions(resolved)
        if missing or stale:
            lines = ["[verify] STALE:"]
            for item in missing:
                lines.append(f"  {item.hole.source_file}:{item.hole.line} reason: missing implementation")
            for item in stale:
                lines.append(f"  {item.hole.source_file}:{item.hole.line} reason: implementation hash changed")
            return False, "\n".join(lines)
        return True, f"[verify] OK: {len(resolved)} holes, {len(resolved)} implementations, 0 stale"

    config = load_config()
    manifest_path = (config.project_root or Path.cwd()) / ".supercode" / "manifest.json"
    if not manifest_path.exists():
        return False, f"[verify] no manifest found at {manifest_path}"
    data = load_manifest(manifest_path)
    stale: list[str] = []
    for item in data.get("holes", []):
        impl = item.get("impl", {})
        path_text = impl.get("path")
        hash_text = impl.get("hash")
        if path_text and hash_text:
            path = Path(path_text)
            if not path.exists():
                stale.append(f"  {item['source_file']}:{item['line']} reason: implementation file missing")
            elif file_sha256(path) != hash_text:
                stale.append(f"  {item['source_file']}:{item['line']} reason: implementation hash changed")
    if stale:
        return False, "\n".join(["[verify] STALE:", *stale])
    return True, f"[verify] OK: {len(data.get('holes', []))} holes, {len(data.get('holes', []))} implementations, 0 stale"
