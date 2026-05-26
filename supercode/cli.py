from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from .build import build_generated_only, build_source, render_compile_command, run_passthrough, run_python_project
from .clean import clean_workdir
from .config import init_config, load_config
from .generator import generate_project
from .init import init_project
from .inspect import inspect_workdir
from .scanner import scan_file

COMMANDS = {"generate", "inspect", "clean", "init-config", "init"}


def _build_compile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="super")
    parser.add_argument("source")
    parser.add_argument("-o", "--output")
    parser.add_argument("--mock", action="store_true")
    return parser


def _build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="super")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("source")
    generate_parser.add_argument("--mock", action="store_true")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--show-source", action="store_true")

    subparsers.add_parser("clean")
    subparsers.add_parser("init-config")
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if argv and argv[0] not in COMMANDS:
        args = _build_compile_parser().parse_args(argv)
        source_path = Path(args.source)
        scan = scan_file(source_path)
        if not scan.holes:
            output = Path(args.output) if args.output else None
            cmd = run_passthrough(source_path, output)
            print(shlex.join(cmd))
            return 0
        if source_path.suffix != ".py" and not args.output:
            raise SystemExit("super: error: source files with holes require -o/--output")
        config = load_config()
        if args.mock:
            print("[SuperCode mock backend] No LLM was called. This run only validates scanner/emitter/build plumbing.")
        project = generate_project(scan, config, mock=args.mock)
        if scan.language == "python":
            build_generated_only(project, config)
            run_python_project(project)
        else:
            build_source(project, config, Path(args.output))
            print(render_compile_command(project, config, Path(args.output)))
        return 0

    parser = _build_command_parser()
    args = parser.parse_args(argv)
    if args.command == "generate":
        scan = scan_file(args.source)
        if not scan.holes:
            print("no SuperCode holes found")
            return 0
        config = load_config()
        if args.mock:
            print("[SuperCode mock backend] No LLM was called. This run only validates scanner/emitter/build plumbing.")
        project = generate_project(scan, config, mock=args.mock)
        build_generated_only(project, config)
        print(project.manifest_path)
        return 0
    if args.command == "inspect":
        print(inspect_workdir(show_source=args.show_source))
        return 0
    if args.command == "clean":
        print(clean_workdir())
        return 0
    if args.command == "init-config":
        print(init_config())
        return 0
    if args.command == "init":
        result = init_project(force=args.force)
        print(result.config_status)
        print(result.clangd_status)
        print(result.pyright_status)
        print(result.ide_header_status)
        for warning in result.warnings:
            print(warning, file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
