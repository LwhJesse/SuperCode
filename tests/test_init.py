import shutil
import subprocess
from pathlib import Path

from supercode.init import init_project
from supercode.paths import get_packaged_include_dir, get_runtime_package_path


ROOT = Path(__file__).resolve().parents[1]


def _write_example_project(root: Path) -> None:
    (root / "include").mkdir(parents=True, exist_ok=True)
    (root / "examples" / "c_export_func").mkdir(parents=True, exist_ok=True)
    (root / "examples" / "c_struct").mkdir(parents=True, exist_ok=True)
    (root / "examples" / "cpp_class").mkdir(parents=True, exist_ok=True)

    (root / "examples" / "c_export_func" / "main.c").write_text(
        '#include <supercode.h>\n'
        'super_export_func(mode_min_tie, int, const int *a, int n);\n'
        'int main(void) { int a[] = {1}; return mode_min_tie(a, 1); }\n',
        encoding="utf-8",
    )
    (root / "examples" / "c_struct" / "main.c").write_text(
        '#include <supercode.h>\n'
        'super_struct(IntVec);\n'
        'int main(void) { IntVec *v = IntVec_create(); return IntVec_size(v); }\n',
        encoding="utf-8",
    )
    (root / "examples" / "cpp_class" / "main.cpp").write_text(
        '#include <supercode.hpp>\n'
        'super_class(LRUCache);\n'
        'int main() { LRUCache c(2); return c.contains(1); }\n',
        encoding="utf-8",
    )
    shutil.copy(ROOT / "include" / "supercode.h", root / "include" / "supercode.h")
    shutil.copy(ROOT / "include" / "supercode.hpp", root / "include" / "supercode.hpp")


def test_super_init_generates_clangd_and_ide_view(tmp_path: Path) -> None:
    _write_example_project(tmp_path)
    result = init_project(tmp_path)
    clangd = (tmp_path / ".clangd").read_text(encoding="utf-8")
    ide = (tmp_path / ".supercode" / "include" / "supercode_ide.h").read_text(encoding="utf-8")

    assert result.config_status == "generated supercode.toml"
    assert result.clangd_status == "generated .clangd"
    assert result.pyright_status == "generated pyrightconfig.json"
    assert result.ide_header_status == "generated .supercode/include/supercode_ide.h"
    assert f"-I{get_packaged_include_dir().resolve()}" in clangd
    assert f"-I{(tmp_path / '.supercode' / 'include').resolve()}" in clangd
    assert "-DSUPERCODE_IDE=1" in clangd
    assert "-include" in clangd
    assert str((tmp_path / ".supercode" / "include" / "supercode_ide.h").resolve()) in clangd
    assert (tmp_path / ".supercode" / "include").is_dir()
    assert (tmp_path / ".supercode" / "impl").is_dir()
    assert not list((tmp_path / ".supercode" / "impl").glob("*.c"))
    assert not list((tmp_path / ".supercode" / "impl").glob("*.cpp"))
    assert "int mode_min_tie(const int * a, int n);" in ide or "int mode_min_tie(const int *a, int n);" in ide
    assert "typedef struct IntVec IntVec;" in ide
    assert "IntVec *IntVec_create(void);" in ide
    assert "class LRUCache {" in ide
    assert "Impl* impl_;" in ide
    pyright = (tmp_path / "pyrightconfig.json").read_text(encoding="utf-8")
    assert ".supercode/bindings/python" in pyright
    assert ".supercode/py_impl" in pyright
    assert str(get_runtime_package_path().resolve()) in pyright


def test_super_init_does_not_overwrite_clangd_without_force(tmp_path: Path) -> None:
    _write_example_project(tmp_path)
    clangd_path = tmp_path / ".clangd"
    pyright_path = tmp_path / "pyrightconfig.json"
    clangd_path.write_text("custom clangd\n", encoding="utf-8")
    pyright_path.write_text('{"custom": true}\n', encoding="utf-8")
    result = init_project(tmp_path)
    assert result.clangd_status == ".clangd already exists. Use `super init --force` to overwrite."
    assert result.pyright_status == "pyrightconfig.json already exists. Use `super init --force` to overwrite."
    assert clangd_path.read_text(encoding="utf-8") == "custom clangd\n"
    assert pyright_path.read_text(encoding="utf-8") == '{"custom": true}\n'


def test_super_init_force_overwrites_clangd_and_config(tmp_path: Path) -> None:
    _write_example_project(tmp_path)
    (tmp_path / ".clangd").write_text("custom clangd\n", encoding="utf-8")
    (tmp_path / "supercode.toml").write_text("[llm]\nprovider='custom'\n", encoding="utf-8")
    result = init_project(tmp_path, force=True)
    assert result.config_status == "generated supercode.toml"
    assert result.clangd_status == "generated .clangd"
    assert result.pyright_status == "generated pyrightconfig.json"
    assert "-DSUPERCODE_IDE=1" in (tmp_path / ".clangd").read_text(encoding="utf-8")


def test_init_clangd_uses_packaged_include(tmp_path: Path) -> None:
    _write_example_project(tmp_path)
    init_project(tmp_path)
    clangd = (tmp_path / ".clangd").read_text(encoding="utf-8")
    assert str(get_packaged_include_dir().resolve()) in clangd


def test_pyrightconfig_contains_runtime_path(tmp_path: Path) -> None:
    _write_example_project(tmp_path)
    init_project(tmp_path)
    pyright = (tmp_path / "pyrightconfig.json").read_text(encoding="utf-8")
    assert str(get_runtime_package_path().resolve()) in pyright


def test_super_init_no_api_key_required_and_no_impl_files(tmp_path: Path, monkeypatch) -> None:
    _write_example_project(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = init_project(tmp_path)
    assert result.warnings == []
    assert (tmp_path / "supercode.toml").exists()
    assert (tmp_path / ".supercode" / "include" / "supercode_ide.h").exists()
    assert not any((tmp_path / ".supercode" / "impl").iterdir())


def test_init_c_export_func_clang_syntax(tmp_path: Path) -> None:
    if shutil.which("clang") is None:
        return
    _write_example_project(tmp_path)
    init_project(tmp_path)
    result = subprocess.run(
        [
            "clang",
            "-fsyntax-only",
            f"-I{(tmp_path / 'include').resolve()}",
            f"-I{(tmp_path / '.supercode' / 'include').resolve()}",
            "-DSUPERCODE_IDE=1",
            "-include",
            str((tmp_path / ".supercode" / "include" / "supercode_ide.h").resolve()),
            str(tmp_path / "examples" / "c_export_func" / "main.c"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_init_c_struct_clang_syntax(tmp_path: Path) -> None:
    if shutil.which("clang") is None:
        return
    _write_example_project(tmp_path)
    init_project(tmp_path)
    result = subprocess.run(
        [
            "clang",
            "-fsyntax-only",
            f"-I{(tmp_path / 'include').resolve()}",
            f"-I{(tmp_path / '.supercode' / 'include').resolve()}",
            "-DSUPERCODE_IDE=1",
            "-include",
            str((tmp_path / ".supercode" / "include" / "supercode_ide.h").resolve()),
            str(tmp_path / "examples" / "c_struct" / "main.c"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_init_cpp_class_clang_syntax(tmp_path: Path) -> None:
    if shutil.which("clang++") is None:
        return
    _write_example_project(tmp_path)
    init_project(tmp_path)
    result = subprocess.run(
        [
            "clang++",
            "-std=c++17",
            "-fsyntax-only",
            f"-I{(tmp_path / 'include').resolve()}",
            f"-I{(tmp_path / '.supercode' / 'include').resolve()}",
            "-DSUPERCODE_IDE=1",
            "-include",
            str((tmp_path / ".supercode" / "include" / "supercode_ide.h").resolve()),
            str(tmp_path / "examples" / "cpp_class" / "main.cpp"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
