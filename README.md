# SuperCode

SuperCode is an experimental AI hole-filling compiler/interpreter frontend.

It does not rewrite your source code.
It only fills explicit `super_func`, `super_export_func`, `super_struct`, and `super_class` holes, stores generated implementations under `.supercode/`, and links or imports them back through `super`.

## Warning

- SuperCode is experimental.
- It calls an LLM.
- It generates code.
- Generated code may be wrong.
- Inspect `.supercode/impl` before trusting generated code.
- Do not use SuperCode for production, security-critical, financial, safety-critical, or unreviewed code paths.

## Installation

Arch Linux:

```bash
yay -S python-supercode-cli-git
```

Linux / macOS:

```bash
uv tool install supercode-cli
```

Alternative:

```bash
pipx install supercode-cli
```

If you know exactly how you want to manage your Python environment, you can also install with `pip`, but `uv tool install` / `pipx` / AUR are the recommended user-facing paths.

Verify:

```bash
super --help
super init
```

Names:

- PyPI distribution name: `supercode-cli`
- AUR package name: `python-supercode-cli-git`
- CLI command: `super`
- Python import name: `supercode`
- C header: `supercode.h`
- C++ header: `supercode.hpp`

## Quick Start

```bash
super init
export OPENROUTER_API_KEY="your_api_key_here"
# edit supercode.toml if needed
super examples/c_local_func/main.c -o /tmp/sc-local
/tmp/sc-local
super inspect
```

## LLM Configuration

SuperCode reads LLM settings from `supercode.toml`.

- Do not put a raw API key into `supercode.toml`.
- `api_key_env` is the name of an environment variable, not the key itself.
- Put the actual key into your shell environment.

OpenRouter + DeepSeek example:

```toml
[llm]
provider = "openai-compatible"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
model = "deepseek/deepseek-v4-pro"
temperature = 0.1
```

```bash
export OPENROUTER_API_KEY="your_api_key_here"
```

DeepSeek direct example:

```toml
[llm]
provider = "openai-compatible"
base_url = "https://api.deepseek.com"
api_key_env = "DEEPSEEK_API_KEY"
model = "deepseek-v4-flash"
temperature = 0.1
```

```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

The `model` field is user-configurable. Change it to match the provider and model you want to use.

## Minimal LLM Config Change

If you only want to change the key, change the environment variable value:

```bash
export OPENROUTER_API_KEY="new_key_here"
```

If you want to switch providers, only change these four fields in `supercode.toml`:

- `provider`
- `base_url`
- `api_key_env`
- `model`

Example:

```toml
[llm]
provider = "openai-compatible"
base_url = "https://your-provider.example/v1"
api_key_env = "YOUR_PROVIDER_API_KEY"
model = "your/model-name"
```

```bash
export YOUR_PROVIDER_API_KEY="your_key_here"
```

## Mock Mode

- `--mock` does not call an LLM.
- `--mock` does not validate AI generation quality.
- `--mock` only validates scanner/emitter/build plumbing.
- Real SuperCode behavior requires a real LLM backend.

Example:

```bash
super examples/c_local_func/main.c -o /tmp/sc-local --mock
```

## C Local `super_func`

```c
#include <stdio.h>
#include <supercode.h>

int mode_min_tie(const int *a, int n) {
    // Return the most frequent element; if there is a tie, return the smallest value.
    return super_func(int, a, n);
}

int main(void) {
    int a[] = {3, 1, 3, 1, 1};
    printf("%d\n", mode_min_tie(a, 5));
    return 0;
}
```

- User source is not rewritten.
- `.supercode/impl` contains only the generated helper implementation.
- It does not contain a copy of the full source file.

## C `super_export_func` and Python Binding

```c
super_export_func(mode_min_tie, int, const int *a, int n);
```

This generates:

- a C implementation
- a shared library
- a Python `ctypes` binding

Python usage:

```python
from supercode_generated import mode_min_tie

print(mode_min_tie([3, 1, 3, 1, 1]))
```

## C `super_struct`

```c
// An int dynamic array with create, destroy, push, get, and size operations.
super_struct(IntVec);
```

- `super_struct(IntVec)` generates an opaque C API.
- The struct layout lives in `.supercode/impl`.
- The user only sees declarations.

## C++ `super_class`

```cpp
#include <iostream>
#include <supercode.hpp>

// A fixed-capacity LRU cache with int keys and double values.
super_class(LRUCache);

int main() {
    LRUCache c(2);
    c.put(1, 3.14);
    std::cout << c.get(1) << "\n";
}
```

- The generated C++ class uses a PImpl-style implementation.
- User source is not rewritten.

## Python Local `sc.super_func`

```python
import supercode as sc

def mode_min_tie(a: list[int]) -> int:
    # Return the most frequent element; if there is a tie, return the smallest value.
    return sc.super_func(int, a)

print(mode_min_tie([3, 1, 3, 1, 1]))
```

- Run Python SuperCode source files with `super file.py`.
- Plain `python file.py` will fail unless a generated registry already exists.
- Runtime dispatch does not call the LLM.

## IDE Support

```bash
super init
```

This generates:

- `supercode.toml`
- `.clangd`
- `pyrightconfig.json`
- `.supercode/include/supercode_ide.h`

Notes:

- Run `super init --force` if you have older generated config files.
- Restart clangd / pyright after `super init --force`.
- `.clangd` uses packaged include paths.
- `pyrightconfig.json` adds runtime and generated paths.

## IDE Troubleshooting

If clangd still reports `supercode.h file not found`, `Type specifier`, or `undeclared function`:

1. Re-run:

```bash
super init --force
```

2. Restart clangd / your LSP client.

3. Confirm that `.clangd` uses absolute packaged include paths.

4. For Python IDE support, confirm that `pyrightconfig.json` contains:
   - `.`
   - `.supercode/bindings/python`
   - `.supercode/py_impl`
   - the SuperCode runtime package path

5. If Python still reports `import not found`, restart pyright / basedpyright / your Python LSP.

6. Validate syntax directly:

```bash
clang -fsyntax-only \
  -I"$PWD/include" \
  -I"$PWD/.supercode/include" \
  -DSUPERCODE_IDE=1 \
  -include "$PWD/.supercode/include/supercode_ide.h" \
  examples/c_export_func/main.c
```

```bash
clang++ -std=c++17 -fsyntax-only \
  -I"$PWD/include" \
  -I"$PWD/.supercode/include" \
  -DSUPERCODE_IDE=1 \
  -include "$PWD/.supercode/include/supercode_ide.h" \
  examples/cpp_class/main.cpp
```

## What SuperCode Does Not Do

- It does not rewrite source files.
- It does not copy full source files into `.supercode`.
- It does not fix syntax errors.
- It does not make bare `gcc`, `g++`, or `python` understand SuperCode holes.
- Use `super`, not bare compilers/interpreters, for files containing SuperCode holes.
- It is not a production compiler.

## Current Support Matrix

Supported:

- C local `super_func`
- C `super_export_func`
- C `super_struct`
- C++ `super_class`
- Python local `sc.super_func`
- Python `ctypes` binding for exported C functions
- clangd / pyright initialization through `super init`

Not yet supported or still experimental:

- CUDA
- Rust
- Java
- full `supermake`
- complex multi-file projects
- complex C/C++ macros/templates
- production use

## Boundaries

- SuperCode does not modify user source files.
- SuperCode does not copy full source files into `.supercode`.
- `.supercode/impl` contains generated implementation units only.
- `super init` does not call an LLM and does not generate implementations.
- The manifest stores locations, hashes, generated symbols, and generated file paths, not raw source lines.
- Generated implementations do not include user source files.
- Generated implementations do not copy user wrapper functions.
- AI generation is limited to explicit holes.

## Super-Fusion Status

`super` is supposed to glue every language into one cursed toolchain.

| Language / Runtime | Super-fused |
| --- | --- |
| C | ✅ |
| Python | ✅ |
| C++ | ✅ partial |
| Rust | ❌ |
| Java | ❌ |
| JavaScript | ❌ |
| TypeScript | ❌ |
| Go | ❌ |
| Zig | ❌ |
| Swift | ❌ |
| Kotlin | ❌ |
| Scala | ❌ |
| C# | ❌ |
| F# | ❌ |
| Objective-C | ❌ |
| Objective-C++ | ❌ |
| CUDA | ❌ |
| HIP | ❌ |
| OpenCL C | ❌ |
| SYCL | ❌ |
| Metal Shading Language | ❌ |
| GLSL | ❌ |
| HLSL | ❌ |
| WGSL | ❌ |
| ISPC | ❌ |
| Fortran | ❌ |
| Julia | ❌ |
| R | ❌ |
| MATLAB | ❌ |
| Octave | ❌ |
| Mathematica / Wolfram Language | ❌ |
| Maple | ❌ |
| SageMath | ❌ |
| Scilab | ❌ |
| Maxima | ❌ |
| LINGO | ❌ |
| GAMS | ❌ |
| AMPL | ❌ |
| MiniZinc | ❌ |
| Modelica | ❌ |
| Simulink | ❌ |
| LabVIEW | ❌ |
| SQL | ❌ |
| PL/pgSQL | ❌ |
| T-SQL | ❌ |
| PL/SQL | ❌ |
| MySQL Stored Programs | ❌ |
| SQLite SQL | ❌ |
| SPARQL | ❌ |
| Cypher | ❌ |
| Datalog | ❌ |
| Prolog | ❌ |
| Mercury | ❌ |
| Erlang | ❌ |
| Elixir | ❌ |
| Gleam | ❌ |
| Haskell | ❌ |
| OCaml | ❌ |
| Standard ML | ❌ |
| F* | ❌ |
| Coq / Gallina | ❌ |
| Lean | ❌ |
| Agda | ❌ |
| Idris | ❌ |
| Futhark | ❌ |
| Elm | ❌ |
| PureScript | ❌ |
| ReasonML | ❌ |
| ReScript | ❌ |
| Clojure | ❌ |
| Common Lisp | ❌ |
| Scheme | ❌ |
| Racket | ❌ |
| Guile | ❌ |
| Emacs Lisp | ❌ |
| AutoLISP | ❌ |
| Lua | ❌ |
| Ruby | ❌ |
| PHP | ❌ |
| Perl | ❌ |
| Raku | ❌ |
| Tcl | ❌ |
| Groovy | ❌ |
| Dart | ❌ |
| CoffeeScript | ❌ |
| LiveScript | ❌ |
| JSX | ❌ |
| TSX | ❌ |
| WebAssembly | ❌ |
| WebAssembly Text / WAT | ❌ |
| Bash | ❌ |
| Zsh | ❌ |
| Fish | ❌ |
| POSIX sh | ❌ |
| PowerShell | ❌ |
| Batch / CMD | ❌ |
| VBScript | ❌ |
| AppleScript | ❌ |
| AutoHotkey | ❌ |
| Make | ❌ |
| CMake | ❌ |
| Meson DSL | ❌ |
| Bazel Starlark | ❌ |
| Ninja | ❌ |
| Dockerfile | ❌ |
| HCL / Terraform | ❌ |
| Nix | ❌ |
| Dhall | ❌ |
| Jsonnet | ❌ |
| YAML | ❌ |
| TOML | ❌ |
| JSON | ❌ |
| XML | ❌ |
| HTML | ❌ |
| CSS | ❌ |
| Sass / SCSS | ❌ |
| Less | ❌ |
| Regex | ❌ |
| AWK | ❌ |
| sed | ❌ |
| M4 | ❌ |
| Vala | ❌ |
| Nim | ❌ |
| Crystal | ❌ |
| D | ❌ |
| V | ❌ |
| Odin | ❌ |
| Jai | ❌ |
| Carbon | ❌ |
| Mojo | ❌ |
| Chapel | ❌ |
| Pony | ❌ |
| Red | ❌ |
| Ring | ❌ |
| Hack | ❌ |
| Haxe | ❌ |
| Fantom | ❌ |
| Eiffel | ❌ |
| Ada | ❌ |
| SPARK | ❌ |
| Pascal | ❌ |
| Delphi / Object Pascal | ❌ |
| Free Pascal | ❌ |
| Modula-2 | ❌ |
| Modula-3 | ❌ |
| Oberon | ❌ |
| BASIC | ❌ |
| Visual Basic | ❌ |
| VB.NET | ❌ |
| QBasic | ❌ |
| FreeBASIC | ❌ |
| COBOL | ❌ |
| RPG | ❌ |
| JCL | ❌ |
| AdaScript | ❌ |
| Assembly | ❌ |
| x86 Assembly | ❌ |
| ARM Assembly | ❌ |
| RISC-V Assembly | ❌ |
| LLVM IR | ❌ |
| MLIR | ❌ |
| Verilog | ❌ |
| SystemVerilog | ❌ |
| VHDL | ❌ |
| Chisel | ❌ |
| Bluespec | ❌ |
| FIRRTL | ❌ |
| Q# | ❌ |
| OpenQASM | ❌ |
| Cirq | ❌ |
| Qiskit circuits | ❌ |
| Solidity | ❌ |
| Vyper | ❌ |
| Move | ❌ |
| Cairo | ❌ |
| Michelson | ❌ |
| Clarity | ❌ |
| Plutus | ❌ |
| DAML | ❌ |
| TeX | ❌ |
| LaTeX | ❌ |
| BibTeX | ❌ |
| Typst | ❌ |
| Markdown | ❌ |
| reStructuredText | ❌ |
| AsciiDoc | ❌ |
| Graphviz DOT | ❌ |
| Mermaid | ❌ |
| PlantUML | ❌ |
| G-code | ❌ |
| PostScript | ❌ |
| Processing | ❌ |
| Arduino | ❌ |
| Scratch | ❌ |
| Blockly | ❌ |
| Logo | ❌ |
| Smalltalk | ❌ |
| Self | ❌ |
| Io | ❌ |
| Forth | ❌ |
| Factor | ❌ |
| APL | ❌ |
| J | ❌ |
| K | ❌ |
| Q / KDB+ | ❌ |
| BQN | ❌ |
| Uiua | ❌ |
| Excel formulas | ❌ |
| Google Sheets formulas | ❌ |
| SAS | ❌ |
| Stata | ❌ |
| SPSS Syntax | ❌ |
| ABAP | ❌ |
| Apex | ❌ |
| PeopleCode | ❌ |
| Progress OpenEdge ABL | ❌ |
| ColdFusion Markup Language | ❌ |
| ActionScript | ❌ |
| UnrealScript | ❌ |
| GDScript | ❌ |
| AngelScript | ❌ |
| Squirrel | ❌ |
| Ren'Py | ❌ |
| Ink | ❌ |
| Inform 7 | ❌ |
| LLVM TableGen | ❌ |
| ANTLR grammar | ❌ |
| Tree-sitter grammar | ❌ |
| Yacc / Bison | ❌ |
| Lex / Flex | ❌ |
| Brainfuck | ❌ |
| Ook! | ❌ |
| Befunge | ❌ |
| Piet | ❌ |
| Whitespace | ❌ |
| INTERCAL | ❌ |
| LOLCODE | ❌ |
| Shakespeare Programming Language | ❌ |
| ArnoldC | ❌ |
| Chef | ❌ |
| Malbolge | ❌ |
| SuperLang, a custom Turing-complete language that does not exist | ❌ |

