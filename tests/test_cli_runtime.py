import os
import tomllib
import shutil
import subprocess
import sys
from pathlib import Path

from supercode.build import render_compile_command, run_passthrough, run_python_project
from supercode.context import GeneratedProject
from supercode.paths import get_packaged_include_dir, get_runtime_package_path
from supercode.scanner import scan_file


ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["HOME"] = str(tmp_path / "home")
    Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
    env.pop("DEEPSEEK_API_KEY", None)
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
    assert not (tmp_path / ".supercode").exists()


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
    assert "[SuperCode mock backend] No LLM was called. This run only validates scanner/emitter/build plumbing." in result.stdout
    assert (tmp_path / ".supercode").exists()
    program = subprocess.run([str(output)], text=True, capture_output=True, check=True)
    assert program.stdout.strip() == "1"


def test_passthrough_with_mock_flag_and_no_holes_stays_passthrough(tmp_path: Path) -> None:
    source = tmp_path / "plain.c"
    output = tmp_path / "plain"
    source.write_text(
        "int main(void) {\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source), "-o", str(output), "--mock")
    assert result.returncode == 0, result.stderr
    assert "[SuperCode mock backend]" not in result.stdout
    assert not (tmp_path / ".supercode").exists()


def test_python_passthrough_without_holes(tmp_path: Path) -> None:
    source = tmp_path / "plain.py"
    source.write_text('print("plain")\n', encoding="utf-8")
    result = _run(tmp_path, str(source))
    assert result.returncode == 0, result.stderr
    assert "plain" in result.stdout
    assert not (tmp_path / ".supercode").exists()


def test_python_hole_without_api_key_fails(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        "import supercode as sc\n\n"
        "def mode_min_tie(a: list[int]) -> int:\n"
        "    return sc.super_func(int, a)\n\n"
        "print(mode_min_tie([1]))\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source))
    assert result.returncode != 0
    assert "SuperCode holes require a real LLM backend. Set DEEPSEEK_API_KEY or configure another provider." in result.stderr


def test_python_hole_with_mock_runs_and_writes_py_impl(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        "import supercode as sc\n\n"
        "def mode_min_tie(a: list[int]) -> int:\n"
        "    # return mode\n"
        "    return sc.super_func(int, a)\n\n"
        "print(mode_min_tie([3, 1, 3, 1, 1]))\n",
        encoding="utf-8",
    )
    result = _run(tmp_path, str(source), "--mock")
    assert result.returncode == 0, result.stderr
    assert "[SuperCode mock backend] No LLM was called. This run only validates scanner/emitter/build plumbing." in result.stdout
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


def test_build_uses_packaged_include(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "include", tmp_path / "include")
    source = tmp_path / "main.c"
    source.write_text(
        "#include <supercode.h>\n"
        "int mode_min_tie(const int *a, int n) { return super_func(int, a, n); }\n"
        "int main(void) { return 0; }\n",
        encoding="utf-8",
    )
    project = GeneratedProject(
        scan=scan_file(source),
        project_root=tmp_path.resolve(),
        source_header=tmp_path / ".supercode" / "include" / "main.sc.h",
        impl_files=[tmp_path / ".supercode" / "impl" / "main.mode_min_tie.2.test.c"],
        manifest_path=tmp_path / ".supercode" / "manifest.json",
        generation_backend="mock",
    )
    project.source_header.parent.mkdir(parents=True, exist_ok=True)
    project.source_header.write_text("#define SUPERCODE_RESOLVED 1\n", encoding="utf-8")
    project.impl_files[0].parent.mkdir(parents=True, exist_ok=True)
    project.impl_files[0].write_text("int __dummy(void){return 0;}\n", encoding="utf-8")
    config_mod = __import__("supercode.config", fromlist=["load_config"])
    command = render_compile_command(project, config_mod.load_config(tmp_path), tmp_path / "out")
    assert str(get_packaged_include_dir().resolve()) in command


def test_python_runtime_path_injected(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "plain.py"
    source.write_text("print('plain')\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(cmd, check, env=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        captured["env"] = env
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_passthrough(source)
    env = captured["env"]
    assert env is not None
    assert str(get_runtime_package_path().resolve()) in env["PYTHONPATH"]


def test_python_runtime_path_injected_for_generated_project(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "main.py"
    source.write_text("print('plain')\n", encoding="utf-8")
    project = GeneratedProject(
        scan=scan_file(source),
        project_root=tmp_path.resolve(),
        source_header=None,
        impl_files=[],
        manifest_path=tmp_path / ".supercode" / "manifest.json",
        generation_backend="mock",
        python_registry=tmp_path / ".supercode" / "python_registry.json",
    )
    project.python_registry.parent.mkdir(parents=True, exist_ok=True)
    project.python_registry.write_text('{"entries":[]}', encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(cmd, check, env=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["env"] = env
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_python_project(project)
    env = captured["env"]
    assert env is not None
    assert str(get_runtime_package_path().resolve()) in env["PYTHONPATH"]
