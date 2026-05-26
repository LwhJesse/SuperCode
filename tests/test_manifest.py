from pathlib import Path

from supercode.context import ImplementationRef, ResolvedHole
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
    )
    resolved = ResolvedHole(
        hole=hole,
        id="IntVec",
        public_name="IntVec",
        signature="super_struct(IntVec)",
        impl=ImplementationRef(
            kind="generated",
            language="c",
            path=".supercode/impl/IntVec.c",
            symbol="IntVec",
            hash="sha256:123",
            backend="mock",
        ),
        artifacts={"header": ".supercode/include/main.sc.h"},
    )
    save_manifest(manifest, [resolved])
    data = load_manifest(manifest)
    assert data["holes"][0]["kind"] == "struct"
    assert data["holes"][0]["impl"]["path"] == ".supercode/impl/IntVec.c"
    assert data["holes"][0]["impl"]["backend"] == "mock"
