from pathlib import Path

from supercode.holes import Hole
from supercode.manifest import load_manifest, save_manifest


def test_manifest_roundtrip(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    hole = Hole(
        kind="struct",
        language="c",
        source_file=Path("main.c"),
        line=4,
        column=1,
        intent="vector",
        source_hash="abc",
        hole_hash="def",
        type_name="IntVec",
        generated_symbol="IntVec",
        impl_path=".supercode/impl/IntVec.c",
    )
    save_manifest(
        manifest,
        [hole],
        generation_backend="mock",
        provider=None,
        model=None,
    )
    data = load_manifest(manifest)
    assert data["holes"][0]["kind"] == "struct"
    assert data["holes"][0]["impl_path"] == ".supercode/impl/IntVec.c"
    assert data["generation"]["backend"] == "mock"
