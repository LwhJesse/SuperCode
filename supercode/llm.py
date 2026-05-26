from __future__ import annotations

import json
import textwrap
import urllib.error
import urllib.request

from .config import Config
from .holes import Hole


def _prompt_for_hole(hole: Hole) -> str:
    kind_constraints = ""
    if hole.kind == "local_func":
        if hole.language == "python":
            kind_constraints = textwrap.dedent(
                f"""
                Required implementation shape:
                - Implement exactly one Python helper function named {hole.generated_symbol}.
                - Function signature must be: def {hole.generated_symbol}({", ".join(p.name for p in hole.typed_params)}):
                - Do not emit the user's outer function {hole.enclosing_function}.
                - Do not emit print statements, script entry points, or module-level demo code.
                """
            ).strip()
        else:
            kind_constraints = textwrap.dedent(
                f"""
                Required implementation shape:
                - Implement exactly one helper function named {hole.generated_symbol}.
                - Function signature must be: {hole.return_type} {hole.generated_symbol}({", ".join(f"{p.type_text} {p.name}" for p in hole.typed_params) or "void"}).
                - Do not emit the user's outer function {hole.enclosing_function}.
                """
            ).strip()
    elif hole.kind == "export_func":
        kind_constraints = textwrap.dedent(
            f"""
            Required implementation shape:
            - Implement exactly one exported C function named {hole.exported_name}.
            - Function signature must be: {hole.return_type} {hole.exported_name}({", ".join(f"{p.type_text} {p.name}" for p in hole.typed_params) or "void"}).
            """
        ).strip()
    elif hole.kind == "struct":
        kind_constraints = textwrap.dedent(
            f"""
            Required implementation shape:
            - Define the opaque struct body as: struct {hole.type_name} {{ ... }};
            - Implement exactly these C symbols and signatures:
              {hole.type_name} *{hole.type_name}_create(void);
              void {hole.type_name}_destroy({hole.type_name} *v);
              void {hole.type_name}_push({hole.type_name} *v, int x);
              int {hole.type_name}_get(const {hole.type_name} *v, int index);
              int {hole.type_name}_size(const {hole.type_name} *v);
            - Do not invent out-parameters or alternate status-code APIs.
            """
        ).strip()
    elif hole.kind == "class":
        kind_constraints = textwrap.dedent(
            f"""
            Required implementation shape:
            - Implement methods for class {hole.type_name} declared elsewhere.
            - Define only struct {hole.type_name}::Impl and these methods:
              {hole.type_name}::{hole.type_name}(int capacity);
              {hole.type_name}::~{hole.type_name}();
              void {hole.type_name}::put(int key, double value);
              double {hole.type_name}::get(int key) const;
              bool {hole.type_name}::contains(int key) const;
            - The private member name is exactly impl_. Use impl_, not pImpl or any other name.
            - Do not emit the class declaration again.
            """
        ).strip()
    return textwrap.dedent(
        f"""
        You are generating one implementation unit for SuperCode.
        Rules:
        - Return JSON only. No markdown.
        - Do not copy user source file.
        - Do not emit main or any outer wrapper function from the user source.
        - Emit only the implementation unit for this hole.
        - Keep the code self-contained and compilable for {hole.language}.
        - If you allocate memory with malloc/calloc/realloc, you must check the failure path.
        - If you allocate with C++ new, you must use an explicit failure-handling strategy such as std::nothrow plus nullptr checks, or a contained try/catch path.
        - Never assume allocation succeeds silently.
        - Follow the exact required signatures below. Do not change parameter lists or return types.

        Hole metadata:
        - language: {hole.language}
        - kind: {hole.kind}
        - symbol: {hole.generated_symbol}
        - exported_name: {hole.exported_name}
        - type_name: {hole.type_name}
        - return_type: {hole.return_type}
        - args: {hole.args}
        - typed_params: {[f"{p.type_text} {p.name}" for p in hole.typed_params]}
        - intent: {hole.intent or "(none)"}

        {kind_constraints}

        JSON schema:
        {{
          "language": "{hole.language}",
          "kind": "{hole.kind}",
          "symbol": "{hole.generated_symbol}",
          "code": "..."
        }}
        """
    ).strip()


def generate_with_llm(config: Config, hole: Hole) -> dict:
    api_key = config.llm.api_key
    if not api_key:
        raise RuntimeError(
            f"environment variable {config.llm.api_key_env} is not set for LLM provider {config.llm.provider}"
        )

    payload = {
        "model": config.llm.model,
        "temperature": config.llm.temperature,
        "messages": [
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": _prompt_for_hole(hole)},
        ],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url=config.llm.base_url.rstrip("/") + "/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        snippet = content[:240].replace("\n", " ")
        raise RuntimeError(f"LLM returned invalid JSON: {snippet}") from exc
    return parsed
