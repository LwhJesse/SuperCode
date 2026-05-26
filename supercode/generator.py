from __future__ import annotations

import re
import textwrap

from .config import Config
from .holes import Hole
from .llm import generate_with_llm

REAL_LLM_REQUIRED_MESSAGE = (
    "SuperCode holes require a real LLM backend. Set DEEPSEEK_API_KEY or configure another provider."
)


def _mock_mode_min_tie(symbol: str) -> str:
    return textwrap.dedent(
        f"""
        #include <stddef.h>

        int {symbol}(const int *a, int n) {{
            if (a == NULL || n <= 0) {{
                return 0;
            }}
            int best_value = a[0];
            int best_count = 0;
            for (int i = 0; i < n; ++i) {{
                int count = 0;
                for (int j = 0; j < n; ++j) {{
                    if (a[j] == a[i]) {{
                        ++count;
                    }}
                }}
                if (count > best_count || (count == best_count && a[i] < best_value)) {{
                    best_count = count;
                    best_value = a[i];
                }}
            }}
            return best_value;
        }}
        """
    ).strip() + "\n"


def _mock_intvec(symbol: str) -> str:
    name = symbol
    return textwrap.dedent(
        f"""
        #include <stdlib.h>

        typedef struct {name} {{
            int *data;
            int size;
            int capacity;
        }} {name};

        {name} *{name}_create(void) {{
            {name} *v = ({name} *)calloc(1, sizeof({name}));
            return v;
        }}

        void {name}_destroy({name} *v) {{
            if (v == NULL) {{
                return;
            }}
            free(v->data);
            free(v);
        }}

        void {name}_push({name} *v, int x) {{
            if (v == NULL) {{
                return;
            }}
            if (v->size == v->capacity) {{
                int next = v->capacity == 0 ? 4 : v->capacity * 2;
                int *resized = (int *)realloc(v->data, (size_t)next * sizeof(int));
                if (resized == NULL) {{
                    return;
                }}
                v->data = resized;
                v->capacity = next;
            }}
            v->data[v->size++] = x;
        }}

        int {name}_get(const {name} *v, int index) {{
            if (v == NULL || index < 0 || index >= v->size) {{
                return 0;
            }}
            return v->data[index];
        }}

        int {name}_size(const {name} *v) {{
            return v == NULL ? 0 : v->size;
        }}
        """
    ).strip() + "\n"


def _mock_lrucache(symbol: str) -> str:
    name = symbol
    return textwrap.dedent(
        f"""
        #include <list>
        #include <unordered_map>
        #include <utility>

        struct {name}::Impl {{
            explicit Impl(int cap) : capacity(cap > 0 ? cap : 1) {{}}

            int capacity;
            std::list<std::pair<int, double>> items;
            std::unordered_map<int, std::list<std::pair<int, double>>::iterator> index;
        }};

        {name}::{name}(int capacity) : impl_(new Impl(capacity)) {{}}

        {name}::~{name}() {{
            delete impl_;
        }}

        void {name}::put(int key, double value) {{
            auto found = impl_->index.find(key);
            if (found != impl_->index.end()) {{
                found->second->second = value;
                impl_->items.splice(impl_->items.begin(), impl_->items, found->second);
                return;
            }}
            impl_->items.emplace_front(key, value);
            impl_->index[key] = impl_->items.begin();
            if ((int)impl_->items.size() > impl_->capacity) {{
                auto last = impl_->items.back();
                impl_->index.erase(last.first);
                impl_->items.pop_back();
            }}
        }}

        double {name}::get(int key) const {{
            auto found = impl_->index.find(key);
            if (found == impl_->index.end()) {{
                return 0.0;
            }}
            impl_->items.splice(impl_->items.begin(), impl_->items, found->second);
            return impl_->items.begin()->second;
        }}

        bool {name}::contains(int key) const {{
            return impl_->index.find(key) != impl_->index.end();
        }}
        """
    ).strip() + "\n"


def generate_mock_payload(hole: Hole) -> dict:
    if hole.kind == "local_func":
        if hole.language == "python":
            symbol = hole.generated_symbol or "generated_symbol"
            code = textwrap.dedent(
                f"""
                def {symbol}(a):
                    if not a:
                        return 0
                    counts = {{}}
                    for item in a:
                        counts[item] = counts.get(item, 0) + 1
                    best_count = max(counts.values())
                    best = min(value for value, count in counts.items() if count == best_count)
                    return best
                """
            ).strip() + "\n"
        else:
            code = _mock_mode_min_tie(hole.generated_symbol or "generated_symbol")
    elif hole.kind == "export_func":
        code = _mock_mode_min_tie(hole.exported_name or hole.generated_symbol or "generated_symbol")
    elif hole.kind == "struct":
        code = _mock_intvec(hole.type_name or "GeneratedStruct")
    elif hole.kind == "class":
        code = _mock_lrucache(hole.type_name or "GeneratedClass")
    else:
        raise ValueError(f"unsupported hole kind: {hole.kind}")
    return {
        "language": hole.language,
        "kind": hole.kind,
        "symbol": hole.generated_symbol,
        "code": code,
    }


def _contains_failure_check_after(code: str, position: int) -> bool:
    window = code[position : position + 320]
    patterns = [
        r"if\s*\(\s*[A-Za-z_]\w*\s*==\s*NULL\s*\)",
        r"if\s*\(\s*NULL\s*==\s*[A-Za-z_]\w*\s*\)",
        r"if\s*\(\s*!\s*[A-Za-z_]\w*\s*\)",
        r"if\s*\(\s*[A-Za-z_]\w*\s*==\s*nullptr\s*\)",
        r"if\s*\(\s*nullptr\s*==\s*[A-Za-z_]\w*\s*\)",
    ]
    return any(re.search(pattern, window) for pattern in patterns)


def _validate_allocation_failure_paths(hole: Hole, code: str) -> None:
    for match in re.finditer(r"\b(?:malloc|calloc|realloc)\s*\(", code):
        if not _contains_failure_check_after(code, match.end()):
            raise RuntimeError(
                f"refusing generated code for {hole.generated_symbol}: allocation without failure-path check"
            )


def _normalize_signature_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _validate_expected_signatures(hole: Hole, code: str) -> None:
    compact = _normalize_signature_text(code)
    if hole.kind == "local_func":
        if hole.language == "python":
            expected = f"def {hole.generated_symbol}({', '.join(p.name for p in hole.typed_params)})"
        else:
            expected = f"{hole.return_type} {hole.generated_symbol}({', '.join(f'{p.type_text} {p.name}' for p in hole.typed_params) or 'void'})"
        if _normalize_signature_text(expected) not in compact:
            raise RuntimeError(f"refusing generated code for {hole.generated_symbol}: signature does not match expected")
    elif hole.kind == "export_func":
        expected = f"{hole.return_type} {hole.exported_name}({', '.join(f'{p.type_text} {p.name}' for p in hole.typed_params) or 'void'})"
        if _normalize_signature_text(expected) not in compact:
            raise RuntimeError(f"refusing generated code for {hole.generated_symbol}: exported signature mismatch")
    elif hole.kind == "struct":
        for snippet in [
            f"struct {hole.type_name}",
            f"{hole.type_name} *{hole.type_name}_create(void)",
            f"void {hole.type_name}_destroy({hole.type_name} *v)",
            f"void {hole.type_name}_push({hole.type_name} *v, int x)",
            f"int {hole.type_name}_get(const {hole.type_name} *v, int index)",
            f"int {hole.type_name}_size(const {hole.type_name} *v)",
        ]:
            if _normalize_signature_text(snippet) not in compact:
                raise RuntimeError(f"refusing generated code for {hole.generated_symbol}: struct API mismatch")
    elif hole.kind == "class":
        for snippet in [
            f"struct {hole.type_name}::Impl",
            f"{hole.type_name}::{hole.type_name}(int capacity)",
            f"{hole.type_name}::~{hole.type_name}()",
            f"void {hole.type_name}::put(int key, double value)",
            f"double {hole.type_name}::get(int key) const",
            f"bool {hole.type_name}::contains(int key) const",
        ]:
            if _normalize_signature_text(snippet) not in compact:
                raise RuntimeError(f"refusing generated code for {hole.generated_symbol}: class API mismatch")


def validate_generated_code(hole: Hole, code: str) -> None:
    if hole.language != "python" and re.search(r"\bmain\s*\(", code):
        raise RuntimeError(f"refusing generated code for {hole.generated_symbol}: contains main()")
    if str(hole.source_file.name) in code:
        raise RuntimeError(f"refusing generated code for {hole.generated_symbol}: references user source file")
    if hole.enclosing_function and (
        re.search(rf"\b{re.escape(hole.enclosing_function)}\s*\(", code)
        or re.search(rf"\bdef\s+{re.escape(hole.enclosing_function)}\s*\(", code)
    ):
        raise RuntimeError(f"refusing generated code for {hole.generated_symbol}: appears to copy user wrapper function")
    _validate_expected_signatures(hole, code)
    if hole.language != "python":
        _validate_allocation_failure_paths(hole, code)


def generate_payloads(config: Config, holes: list[Hole], *, mock: bool) -> dict[str, str]:
    if not mock and not config.llm.api_key:
        raise RuntimeError(REAL_LLM_REQUIRED_MESSAGE)
    payloads: dict[str, str] = {}
    for hole in holes:
        payload = generate_mock_payload(hole) if mock else generate_with_llm(config, hole)
        code = payload.get("code", "")
        if not code.strip():
            raise RuntimeError(f"generator returned empty code for {hole.generated_symbol}")
        validate_generated_code(hole, code)
        payloads[hole.hole_hash] = code
    return payloads
