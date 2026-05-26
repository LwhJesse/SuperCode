from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from .artifacts import assemble_build_project, write_generated_impls
from .build import build_generated_only, build_source, render_compile_command, run_passthrough, run_python_project
from .clean import clean_workdir
from .config import init_config, load_config
from .context import ImplementationRef
from .generator import REAL_LLM_REQUIRED_MESSAGE, generate_payloads
from .init import init_project
from .inspect import inspect_workdir
from .manifest import save_manifest
from .resolver import missing_imports, missing_resolutions, resolve_scan
from .scanner import scan_file
from .verify import verify_project

COMMANDS = {"build", "generate", "inspect", "clean", "init-config", "init", "verify", "regenerate"}


def _build_common_source_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source")
    parser.add_argument("-o", "--output")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")


def _build_compile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="super")
    _build_common_source_parser(parser)
    return parser


def _build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="super")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate")
    _build_common_source_parser(generate_parser)

    regenerate_parser = subparsers.add_parser("regenerate")
    _build_common_source_parser(regenerate_parser)

    build_parser = subparsers.add_parser("build")
    _build_common_source_parser(build_parser)
    build_parser.add_argument("--generate-missing", action="store_true")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--show-source", action="store_true")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("source", nargs="?")

    subparsers.add_parser("clean")
    subparsers.add_parser("init-config")
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--force", action="store_true")
    return parser


def _phase(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def _missing_error(resolved_holes: list, *, phase: str) -> RuntimeError:
    lines = [f"SuperCode {phase} failed.", "Missing implementation:"]
    for item in missing_resolutions(resolved_holes):
        lines.append(f"  source: {item.hole.source_file}")
        lines.append(f"  hole: {item.hole.enclosing_function or item.public_name or item.hole.generated_symbol}: {item.signature}")
    lines.append("Run `super generate ...` or register a handwritten implementation.")
    return RuntimeError("\n".join(lines))


def _import_error(resolved_holes: list) -> RuntimeError:
    lines = ["SuperCode import resolution failed.", "Missing export:"]
    for item in missing_imports(resolved_holes):
        lines.append(f"  source: {item.hole.source_file}")
        lines.append(f"  import: {item.hole.imported_name}")
    return RuntimeError("\n".join(lines))


def _prepare_project(
    source_path: Path,
    *,
    mock: bool,
    offline: bool,
    regenerate: bool,
    allow_generate: bool,
    quiet: bool,
) -> tuple:
    scan = scan_file(source_path)
    config = load_config(source_path)
    resolved = resolve_scan(scan, config)
    _phase(f"[scan] found {len(scan.holes)} SuperCode holes", quiet)
    unresolved_imports = missing_imports(resolved)
    if unresolved_imports:
        raise _import_error(resolved)

    if regenerate:
        targets = []
        for item in resolved:
            if item.hole.kind == "import_func":
                continue
            if item.impl.kind == "handwritten":
                raise RuntimeError(f"refusing to regenerate handwritten implementation: {item.id}")
            targets.append(item)
    else:
        targets = missing_resolutions(resolved)

    for item in resolved:
        if item.impl.kind == "generated":
            _phase(f"[reuse] {item.public_name or item.id} -> {item.impl.path}", quiet)
        elif item.impl.kind == "handwritten":
            _phase(f"[reuse] {item.public_name or item.id} -> {item.impl.path}", quiet)

    if targets:
        if offline or not allow_generate:
            if offline:
                _phase("[offline] missing implementation detected", quiet)
            raise _missing_error(resolved, phase="offline build" if offline else "build")
        if not mock and not config.llm.api_key:
            raise RuntimeError(REAL_LLM_REQUIRED_MESSAGE)
        provider_name = "mock" if mock else f"{config.llm.provider}/{config.llm.model}"
        for item in targets:
            _phase(f"[generate] {item.public_name or item.id} using {provider_name}", quiet)
            item.impl = ImplementationRef(
                kind="generated",
                language=item.hole.language,
                symbol=item.hole.generated_symbol,
                backend="mock" if mock else "real_llm",
                provider=None if mock else config.llm.provider,
                model=None if mock else config.llm.model,
            )
        payloads = generate_payloads(config, [item.hole for item in targets], mock=mock)
        project = assemble_build_project(scan, config, resolved)
        write_generated_impls(project.project_root, payloads, resolved)
        project = assemble_build_project(scan, config, resolved)
        for item in targets:
            _phase(f"[write] {item.impl.path}", quiet)
    else:
        project = assemble_build_project(scan, config, resolved)

    project.manifest_path = save_manifest(project.manifest_path, resolved)
    return scan, config, resolved, project


def _run_super_source(
    source_path: Path,
    output: Path | None,
    *,
    mock: bool,
    offline: bool,
    regenerate: bool,
    allow_generate: bool,
    quiet: bool,
    verbose: bool,
) -> int:
    scan = scan_file(source_path)
    config = load_config(source_path)
    if not scan.holes:
        cmd = run_passthrough(source_path, output, config=config)
        if verbose and not quiet:
            print(f"[build] {shlex.join(cmd)}")
        return 0
    if source_path.suffix != ".py" and output is None:
        raise SystemExit("super: error: source files with holes require -o/--output")
    if mock:
        _phase("[SuperCode mock backend] No LLM was called. This run only validates scanner/emitter/build plumbing.", quiet)
    _, config, _, project = _prepare_project(
        source_path,
        mock=mock,
        offline=offline,
        regenerate=regenerate,
        allow_generate=allow_generate,
        quiet=quiet,
    )
    if scan.language == "python":
        build_generated_only(project, config)
        run_python_project(project, config)
        _phase(f"[done] {project.scan.source_file}", quiet)
    else:
        build_source(project, config, output, quiet=quiet, verbose=verbose)
        if verbose:
            _phase(f"[build] {render_compile_command(project, config, output)}", quiet)
        _phase(f"[done] {output}", quiet)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if argv and argv[0] not in COMMANDS:
        args = _build_compile_parser().parse_args(argv)
        return _run_super_source(
            Path(args.source),
            Path(args.output) if args.output else None,
            mock=args.mock,
            offline=args.offline,
            regenerate=args.regenerate,
            allow_generate=True,
            quiet=args.quiet,
            verbose=args.verbose,
        )

    parser = _build_command_parser()
    args = parser.parse_args(argv)
    if args.command in {"generate", "regenerate"}:
        if args.offline:
            raise RuntimeError("`super generate` does not support --offline because generation requires a provider.")
        scan = scan_file(args.source)
        if not scan.holes:
            print("no SuperCode holes found")
            return 0
        if args.mock:
            print("[SuperCode mock backend] No LLM was called. This run only validates scanner/emitter/build plumbing.")
        _, _, _, project = _prepare_project(
            Path(args.source),
            mock=args.mock,
            offline=False,
            regenerate=args.regenerate or args.command == "regenerate",
            allow_generate=True,
            quiet=args.quiet,
        )
        print(project.manifest_path)
        return 0
    if args.command == "build":
        return _run_super_source(
            Path(args.source),
            Path(args.output) if args.output else None,
            mock=args.mock,
            offline=args.offline or not args.generate_missing,
            regenerate=args.regenerate,
            allow_generate=args.generate_missing,
            quiet=args.quiet,
            verbose=args.verbose,
        )
    if args.command == "inspect":
        print(inspect_workdir(show_source=args.show_source))
        return 0
    if args.command == "verify":
        ok, message = verify_project(args.source)
        print(message)
        return 0 if ok else 1
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
