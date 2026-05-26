from pathlib import Path

from supercode.scanner import scan_file


def test_scan_local_super_func(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    source.write_text(
        '#include <supercode.h>\n'
        'int mode_min_tie(const int *a, int n) {\n'
        '    // tie breaker\n'
        '    return super_func(int, a, n);\n'
        '}\n',
        encoding="utf-8",
    )
    result = scan_file(source)
    assert len(result.holes) == 1
    hole = result.holes[0]
    assert hole.kind == "local_func"
    assert hole.enclosing_function == "mode_min_tie"
    assert hole.intent == "tie breaker"
    assert hole.generated_symbol.startswith("__sc_main_mode_min_tie_")


def test_scan_export_struct_and_class(tmp_path: Path) -> None:
    source = tmp_path / "api.c"
    source.write_text(
        '#include <supercode.h>\n'
        '// exported mode\n'
        'super_export_func(mode_min_tie, int, const int *a, int n);\n'
        'super_struct(IntVec);\n',
        encoding="utf-8",
    )
    result = scan_file(source)
    assert [hole.kind for hole in result.holes] == ["export_func", "struct"]
