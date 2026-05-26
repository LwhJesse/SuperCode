import os
import subprocess
import sys
import tomllib
import shutil
from pathlib import Path

from supercode.build import run_passthrough
from supercode.paths import get_packaged_include_dir, get_runtime_package_path


ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["HOME"] = str(tmp_path / "home")
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("SUPERCODE_LLM_API_KEY_ENV", None)
    env.pop("SUPERCODE_WORKDIR", None)
    return env


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "supercode.cli", *args],
        cwd=tmp_path,
        env=_env(tmp_path),
        text=True,
        capture_output=True,
    )


def test_passthrough_c_without_holes_does_not_generate_workdir(tmp_path: Path) -> None:
    source = tmp_path / "plain.c"
    output = tmp_path / "plain"
    source.write_text(
        "#include <stdio.h>\n"
        "int main(void) {\n"
        '    puts("plain");\n'
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source), "-o", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert not (tmp_path / ".supercode").exists()
    program = subprocess.run([str(output)], text=True, capture_output=True, check=True)
    assert program.stdout.strip() == "plain"


def test_holes_without_api_key_fail_without_mock(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    output = tmp_path / "main"
    source.write_text(
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) {\n"
        "    return super_func(int, a, n);\n"
        "}\n"
        "int main(void) { return 0; }\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source), "-o", str(output))
    assert result.returncode != 0
    assert "SuperCode holes require a real LLM backend. Set DEEPSEEK_API_KEY or configure another provider." in result.stderr


def test_holes_with_explicit_mock_succeed_and_emit_warning(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    output = tmp_path / "main"
    source.write_text(
        "#include <stdio.h>\n"
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) {\n"
        "    // return mode\n"
        "    return super_func(int, a, n);\n"
        "}\n"
        "int main(void) {\n"
        "    int a[] = {3, 1, 3, 1, 1};\n"
        '    printf("%d\\n", mode_min_tie(a, 5));\n'
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source), "-o", str(output), "--mock")
    assert result.returncode == 0, result.stderr
    assert "[SuperCode mock backend]" in result.stderr
    assert "[scan]" in result.stderr
    program = subprocess.run([str(output)], text=True, capture_output=True, check=True)
    assert program.stdout.strip() == "1"


def test_python_passthrough_without_holes(tmp_path: Path) -> None:
    source = tmp_path / "plain.py"
    source.write_text('print("plain")\n', encoding="utf-8")
    result = _run(tmp_path, str(source))
    assert result.returncode == 0, result.stderr
    assert "plain" in result.stdout
    assert not (tmp_path / ".supercode").exists()


def test_python_hole_with_mock_runs_and_writes_py_impl(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        "import supercode as sc\n\n"
        "def mode_min_tie(a: list[int]) -> int:\n"
        "    return sc.super_func(int, a)\n\n"
        "print(mode_min_tie([3, 1, 3, 1, 1]))\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source), "--mock")
    assert result.returncode == 0, result.stderr
    assert "1" in result.stdout
    py_impl_files = list((tmp_path / ".supercode" / "py_impl").glob("*.py"))
    assert py_impl_files
    impl_text = py_impl_files[0].read_text(encoding="utf-8")
    assert "def mode_min_tie" not in impl_text
    assert "print(" not in impl_text


def test_direct_python_run_without_registry_fails_cleanly(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        "import supercode as sc\n\n"
        "def mode_min_tie(a: list[int]) -> int:\n"
        "    return sc.super_func(int, a)\n\n"
        "print(mode_min_tie([1]))\n",
        encoding="utf-8",
    )
    env = _env(tmp_path)
    result = subprocess.run(
        [sys.executable, str(source)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "supercode.super_func was called without generated implementation. Run this file with `super`." in result.stderr


def test_console_script_metadata() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["super"] == "supercode.cli:main"


def test_packaged_include_exists() -> None:
    include_dir = get_packaged_include_dir()
    assert include_dir.is_dir()
    assert (include_dir / "supercode.h").exists()
    assert (include_dir / "supercode.hpp").exists()


def test_python_runtime_path_injected(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "plain.py"
    source.write_text("print('plain')\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(cmd, check, env=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["env"] = env
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_passthrough(source)
    env = captured["env"]
    assert env is not None
    assert str(get_runtime_package_path().resolve()) in env["PYTHONPATH"]


def test_offline_missing_implementation_fails_clearly(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    output = tmp_path / "main"
    source.write_text(
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) {\n"
        "    return super_func(int, a, n);\n"
        "}\n"
        "int main(void) { return 0; }\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, "build", str(source), "-o", str(output), "--offline")
    assert result.returncode != 0
    assert "SuperCode offline build failed." in result.stderr
    assert "Missing implementation:" in result.stderr


def test_generate_only_writes_impl_without_building_binary(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    output = tmp_path / "main"
    source.write_text(
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) {\n"
        "    return super_func(int, a, n);\n"
        "}\n"
        "int main(void) { return 0; }\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, "generate", str(source), "--mock")
    assert result.returncode == 0, result.stderr
    assert not output.exists()
    assert list((tmp_path / ".supercode" / "impl").glob("*.c"))


def test_reuse_existing_generated_impl_without_mock_or_api_key(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    output = tmp_path / "main"
    source.write_text(
        "#include <stdio.h>\n"
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) {\n"
        "    return super_func(int, a, n);\n"
        "}\n"
        "int main(void) {\n"
        "    int a[] = {3, 1, 3, 1, 1};\n"
        '    printf("%d\\n", mode_min_tie(a, 5));\n'
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    first = _run(tmp_path, "generate", str(source), "--mock")
    assert first.returncode == 0, first.stderr
    second = _run(tmp_path, "build", str(source), "-o", str(output), "--offline")
    assert second.returncode == 0, second.stderr
    assert "[generate]" not in second.stderr
    program = subprocess.run([str(output)], text=True, capture_output=True, check=True)
    assert program.stdout.strip() == "1"


def test_regenerate_refuses_handwritten_implementation(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    shutil.copytree(ROOT / "examples" / "no_ai", project)
    shutil.copy(ROOT / "include" / "supercode.h", project / "include.h")
    result = _run(tmp_path, "regenerate", str(project / "c_export" / "main.c"), "--mock")
    assert result.returncode != 0
    assert "refusing to regenerate handwritten implementation: mode_min_tie" in result.stderr


def test_verify_valid_manifest_and_detect_missing_impl(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    source.write_text(
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) { return super_func(int, a, n); }\n"
        "int main(void) { return 0; }\n",
        encoding="utf-8",
    )
    generated = _run(tmp_path, "generate", str(source), "--mock")
    assert generated.returncode == 0, generated.stderr
    ok = _run(tmp_path, "verify", str(source))
    assert ok.returncode == 0, ok.stderr
    impl = next((tmp_path / ".supercode" / "impl").glob("*.c"))
    impl.unlink()
    bad = _run(tmp_path, "verify", str(source))
    assert bad.returncode != 0
    assert "[verify] STALE:" in bad.stdout


def test_no_ai_examples_work_offline(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "examples" / "no_ai", tmp_path / "no_ai")
    c_out = tmp_path / "sc-c"
    cpp_out = tmp_path / "sc-cpp"

    c_result = _run(tmp_path, "build", str(tmp_path / "no_ai" / "c_export" / "main.c"), "-o", str(c_out), "--offline")
    assert c_result.returncode == 0, c_result.stderr
    assert subprocess.run([str(c_out)], text=True, capture_output=True, check=True).stdout.strip() == "1"

    cpp_result = _run(tmp_path, "build", str(tmp_path / "no_ai" / "cpp_import" / "main.cpp"), "-o", str(cpp_out), "--offline")
    assert cpp_result.returncode == 0, cpp_result.stderr
    assert subprocess.run([str(cpp_out)], text=True, capture_output=True, check=True).stdout.strip() == "1"

    py_result = _run(tmp_path, "build", str(tmp_path / "no_ai" / "python_import" / "main.py"), "--offline")
    assert py_result.returncode == 0, py_result.stderr
    assert py_result.stdout.strip() == "1"


def test_verbose_shows_build_command(tmp_path: Path) -> None:
    source = tmp_path / "plain.c"
    output = tmp_path / "plain"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    result = _run(tmp_path, str(source), "-o", str(output), "--verbose")
    assert result.returncode == 0, result.stderr
    assert "[build]" in result.stdout or "[build]" in result.stderr


def test_quiet_reduces_phase_output(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    output = tmp_path / "main"
    source.write_text(
        "#include <stdio.h>\n"
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) { return super_func(int, a, n); }\n"
        "int main(void) { int a[] = {1}; printf(\"%d\\n\", mode_min_tie(a, 1)); return 0; }\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source), "-o", str(output), "--mock", "--quiet")
    assert result.returncode == 0, result.stderr
    assert "[scan]" not in result.stdout
