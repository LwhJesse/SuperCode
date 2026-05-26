from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from .holes import FunctionContext, FunctionParam, Hole, ScanResult

CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch"}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_args(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in text:
        if ch == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        if ch in "(<[{":
            depth += 1
        elif ch in ")>]}":
            depth = max(depth - 1, 0)
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _parse_param(part: str) -> FunctionParam | None:
    clean = part.strip()
    if not clean or clean == "void":
        return None
    match = re.match(r"(?P<type>.+?)(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])?$", clean)
    if not match:
        return None
    type_text = match.group("type").strip()
    name = match.group("name").strip()
    if not type_text.endswith(("*", "&")):
        type_text = re.sub(r"\s+", " ", type_text).strip()
    return FunctionParam(type_text=type_text, name=name)


def _parse_params(text: str) -> list[FunctionParam]:
    params: list[FunctionParam] = []
    for item in _split_args(text):
        parsed = _parse_param(item)
        if parsed:
            params.append(parsed)
    return params


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _col_number(text: str, offset: int) -> int:
    line_start = text.rfind("\n", 0, offset)
    return offset + 1 if line_start == -1 else offset - line_start


def _extract_functions(text: str) -> list[FunctionContext]:
    pattern = re.compile(
        r"(?P<signature>(?P<ret>[A-Za-z_~][\w:\s<>\*&:,]*?)\b(?P<name>[A-Za-z_~]\w*)\s*\((?P<params>[^;{}()]*)\)\s*(?:const\s*)?\{)",
        re.MULTILINE,
    )
    functions: list[FunctionContext] = []
    for match in pattern.finditer(text):
        name = match.group("name")
        if name in CONTROL_KEYWORDS:
            continue
        start = match.start("signature")
        brace_pos = match.end("signature") - 1
        depth = 0
        end = None
        for index in range(brace_pos, len(text)):
            ch = text[index]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end is None:
            continue
        functions.append(
            FunctionContext(
                name=name,
                return_type=re.sub(r"\s+", " ", match.group("ret")).strip(),
                params=_parse_params(match.group("params")),
                start_line=_line_number(text, start),
                end_line=_line_number(text, end),
            )
        )
    return functions


def _find_enclosing_function(line: int, functions: list[FunctionContext]) -> FunctionContext | None:
    candidates = [fn for fn in functions if fn.start_line <= line <= fn.end_line]
    if not candidates:
        return None
    return sorted(candidates, key=lambda fn: (fn.end_line - fn.start_line, fn.start_line))[0]


def _collect_comment(lines: list[str], line_index: int, marker: str) -> str:
    comments: list[str] = []
    current = line_index - 1
    while current >= 0:
        stripped = lines[current].strip()
        if stripped.startswith(marker):
            comments.append(stripped[len(marker) :].strip())
            current -= 1
            continue
        if stripped == "":
            current -= 1
            continue
        break
    comments.reverse()
    return " ".join(comments)


def _hole_hash(
    source_file: Path,
    line: int,
    column: int,
    enclosing_function: str | None,
    kind: str,
    parts: list[str],
) -> str:
    basis = "|".join(
        [
            str(source_file.resolve()),
            str(line),
            str(column),
            enclosing_function or "",
            kind,
            *parts,
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8]


def _symbol_prefix(source_file: Path) -> str:
    stem = re.sub(r"\W+", "_", source_file.stem)
    return stem.strip("_") or "source"


def _annotation_text(node: ast.expr | None) -> str:
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        return "Any"


def _scan_python_file(path: Path, text: str, source_hash: str) -> ScanResult:
    tree = ast.parse(text, filename=str(path))
    lines = text.splitlines()
    holes: list[Hole] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            exported = any(
                isinstance(decorator, ast.Attribute) and decorator.attr == "super_export"
                for decorator in node.decorator_list
            )
            if exported:
                holes.append(
                    Hole(
                        kind="python_export_func",
                        language="python",
                        source_file=path,
                        line=node.lineno,
                        column=node.col_offset + 1,
                        intent=_collect_comment(lines, node.lineno - 1, "#"),
                        source_hash=source_hash,
                        hole_hash=_hole_hash(
                            path,
                            node.lineno,
                            node.col_offset + 1,
                            node.name,
                            "python_export_func",
                            [
                                node.name,
                                _annotation_text(node.returns),
                                *(
                                    f"{_annotation_text(arg.annotation)}:{arg.arg}"
                                    for arg in node.args.args
                                ),
                            ],
                        ),
                        enclosing_function=node.name,
                        return_type=_annotation_text(node.returns),
                        typed_params=[
                            FunctionParam(type_text=_annotation_text(arg.annotation), name=arg.arg)
                            for arg in node.args.args
                        ],
                        exported_name=node.name,
                        generated_symbol=node.name,
                    )
                )
            self.stack.append(node)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.stack.append(node)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and node.func.attr == "super_func":
                if not self.stack:
                    raise ValueError(f"super_func at {path}:{node.lineno} is not inside a function")
                if len(node.args) < 1:
                    raise ValueError(f"super_func at {path}:{node.lineno} is missing return type")
                enclosing = self.stack[-1]
                typed_params = [
                    FunctionParam(type_text=_annotation_text(arg.annotation), name=arg.arg)
                    for arg in enclosing.args.args
                ]
                try:
                    return_type = ast.unparse(node.args[0])
                except Exception:
                    return_type = "Any"
                arg_texts = []
                for arg in node.args[1:]:
                    try:
                        arg_texts.append(ast.unparse(arg))
                    except Exception:
                        arg_texts.append("arg")
                hole_hash = _hole_hash(
                    path,
                    node.lineno,
                    node.col_offset + 1,
                    enclosing.name,
                    "local_func",
                    [return_type, *arg_texts, *(f"{p.type_text}:{p.name}" for p in typed_params)],
                )
                symbol = f"__sc_{_symbol_prefix(path)}_{enclosing.name}_{node.lineno}_{hole_hash}"
                holes.append(
                    Hole(
                        kind="local_func",
                        language="python",
                        source_file=path,
                        line=node.lineno,
                        column=node.col_offset + 1,
                        intent=_collect_comment(lines, node.lineno - 1, "#"),
                        source_hash=source_hash,
                        hole_hash=hole_hash,
                        enclosing_function=enclosing.name,
                        return_type=return_type,
                        args=arg_texts,
                        typed_params=typed_params,
                        generated_symbol=symbol,
                    )
                )
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_func":
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise ValueError(f"import_func at {path}:{node.lineno} requires a string export name")
                imported_name = node.args[0].value
                hole_hash = _hole_hash(
                    path,
                    node.lineno,
                    node.col_offset + 1,
                    None,
                    "import_func",
                    [imported_name],
                )
                holes.append(
                    Hole(
                        kind="import_func",
                        language="python",
                        source_file=path,
                        line=node.lineno,
                        column=node.col_offset + 1,
                        intent="",
                        source_hash=source_hash,
                        hole_hash=hole_hash,
                        imported_name=imported_name,
                        generated_symbol=imported_name,
                    )
                )
            self.generic_visit(node)

    Visitor().visit(tree)
    holes.sort(key=lambda item: (item.line, item.column))
    return ScanResult(source_file=path, language="python", source_hash=source_hash, holes=holes)


def _scan_super_func(
    match: re.Match[str],
    text: str,
    lines: list[str],
    source_file: Path,
    language: str,
    source_hash: str,
    functions: list[FunctionContext],
) -> Hole:
    line = _line_number(text, match.start())
    column = _col_number(text, match.start())
    enclosing = _find_enclosing_function(line, functions)
    if enclosing is None:
        raise ValueError(f"super_func at {source_file}:{line} is not inside a function")
    args = _split_args(match.group("args"))
    return_type = match.group("return").strip()
    hole_hash = _hole_hash(
        source_file,
        line,
        column,
        enclosing.name,
        "local_func",
        [return_type, *args, *(f"{p.type_text}:{p.name}" for p in enclosing.params)],
    )
    symbol = f"__sc_{_symbol_prefix(source_file)}_{enclosing.name}_{line}_{hole_hash}"
    return Hole(
        kind="local_func",
        language=language,  # type: ignore[arg-type]
        source_file=source_file,
        line=line,
        column=column,
        intent=_collect_comment(lines, line - 1, "//"),
        source_hash=source_hash,
        hole_hash=hole_hash,
        enclosing_function=enclosing.name,
        return_type=return_type,
        args=args,
        typed_params=enclosing.params,
        generated_symbol=symbol,
    )


def _scan_named_func(
    kind: str,
    match: re.Match[str],
    text: str,
    lines: list[str],
    source_file: Path,
    language: str,
    source_hash: str,
) -> Hole:
    line = _line_number(text, match.start())
    column = _col_number(text, match.start())
    name = match.group("name").strip()
    return_type = match.group("return").strip()
    typed_params = _parse_params(match.group("params") or "")
    hole_hash = _hole_hash(
        source_file,
        line,
        column,
        None,
        kind,
        [name, return_type, *(f"{p.type_text}:{p.name}" for p in typed_params)],
    )
    return Hole(
        kind=kind,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
        source_file=source_file,
        line=line,
        column=column,
        intent=_collect_comment(lines, line - 1, "//"),
        source_hash=source_hash,
        hole_hash=hole_hash,
        return_type=return_type,
        typed_params=typed_params,
        exported_name=name if kind == "export_func" else None,
        imported_name=name if kind == "import_func" else None,
        generated_symbol=name,
    )


def _scan_named_type(
    kind: str,
    match: re.Match[str],
    text: str,
    lines: list[str],
    source_file: Path,
    language: str,
    source_hash: str,
) -> Hole:
    line = _line_number(text, match.start())
    column = _col_number(text, match.start())
    type_name = match.group("name").strip()
    hole_hash = _hole_hash(source_file, line, column, None, kind, [type_name])
    return Hole(
        kind=kind,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
        source_file=source_file,
        line=line,
        column=column,
        intent=_collect_comment(lines, line - 1, "//"),
        source_hash=source_hash,
        hole_hash=hole_hash,
        type_name=type_name,
        generated_symbol=type_name,
    )


def scan_file(source_file: str | Path) -> ScanResult:
    path = Path(source_file).resolve()
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".cpp", ".cc", ".cxx"}:
        language = "cpp"
    elif path.suffix == ".py":
        language = "python"
    else:
        language = "c"
    source_hash = _sha256_text(text)
    if language == "python":
        return _scan_python_file(path, text, source_hash)

    lines = text.splitlines()
    functions = _extract_functions(text)
    holes: list[Hole] = []
    for match in re.finditer(r"super_func\s*\(\s*(?P<return>[^,]+)\s*,\s*(?P<args>[^)]*)\)", text):
        holes.append(_scan_super_func(match, text, lines, path, language, source_hash, functions))
    for match in re.finditer(
        r"super_export_func\s*\(\s*(?P<name>[A-Za-z_]\w*)\s*,\s*(?P<return>[^,]+)\s*(?:,\s*(?P<params>[^)]*))?\)",
        text,
    ):
        holes.append(_scan_named_func("export_func", match, text, lines, path, language, source_hash))
    for match in re.finditer(
        r"super_import_func\s*\(\s*(?P<name>[A-Za-z_]\w*)\s*,\s*(?P<return>[^,]+)\s*(?:,\s*(?P<params>[^)]*))?\)",
        text,
    ):
        holes.append(_scan_named_func("import_func", match, text, lines, path, language, source_hash))
    for match in re.finditer(r"super_struct\s*\(\s*(?P<name>[A-Za-z_]\w*)\s*\)", text):
        holes.append(_scan_named_type("struct", match, text, lines, path, language, source_hash))
    for match in re.finditer(r"super_class\s*\(\s*(?P<name>[A-Za-z_]\w*)\s*\)", text):
        holes.append(_scan_named_type("class", match, text, lines, path, language, source_hash))

    holes.sort(key=lambda item: (item.line, item.column))
    return ScanResult(source_file=path, language=language, source_hash=source_hash, holes=holes)
