# SuperCode v1 Syntax

SuperCode v1 fixes the non-AI surface syntax and the deterministic glue rules.

`super` is the glue.
The LLM only fills the holes.

## Stable Syntax

### C / C++ local expression hole

```c
return super_func(ReturnType, arg1, arg2, ...);
```

- `super_func` is a local expression hole.
- It resolves to a hidden helper chosen by `super`.
- It is not exported and not cross-language by default.
- Existing implementations are reused.
- Missing implementations may be generated unless `--offline` is active.

### C / C++ exported function

```c
super_export_func(Name, ReturnType, typed_params...);
```

- Declares a public SuperCode export.
- The stable public name is `Name`.
- Cross-language glue is built around the export registry.
- Handwritten implementations may be registered in `supercode.toml`.

### C / C++ imported function

```c
super_import_func(Name, ReturnType, typed_params...);
```

- Declares that the current translation unit consumes a SuperCode export.
- It does not generate an implementation.
- Import resolution must find a matching export implementation.

### C opaque struct

```c
super_struct(Name);
```

v1 preserves the fixed opaque API contract:

```c
typedef struct Name Name;
Name *Name_create(void);
void Name_destroy(Name *v);
void Name_push(Name *v, int x);
int Name_get(const Name *v, int index);
int Name_size(const Name *v);
```

### C++ class

```cpp
super_class(Name);
```

- v1 preserves the current PImpl-style class contract.
- The implementation may be generated or handwritten.
- Cross-language object ABI is not part of v1.

### Python local hole

```python
import supercode as sc

def f(...):
    return sc.super_func(ReturnType, arg1, arg2, ...)
```

- Runtime dispatch only uses the prepared registry.
- Runtime never calls the LLM.

### Python exported function

```python
import supercode as sc

@sc.super_export
def name(...) -> ReturnType:
    ...
```

- This is the stable Python export syntax.
- Python export to C/C++ is not implemented in v1.

### Python imported function

```python
func = sc.import_func("Name")
func = sc.import_func("Name", returns=int, args=[list[int]])
```

- This is the stable Python import API.
- Python import consumes the SuperCode export registry.

## Deterministic Rules

- No holes: `super` passes through to the real compiler or interpreter.
- Holes with existing implementations: `super` reuses them and does not call the LLM.
- Holes with missing implementations:
  - default `super file...` may generate;
  - `super build ...` is reuse-only by default;
  - `--offline` forbids generation;
  - `--regenerate` forces regeneration of generated implementations;
  - handwritten implementations are never overwritten by regeneration.

## Implementation Artifacts

SuperCode v1 distinguishes four implementation states:

1. `generated`
2. `handwritten`
3. `external`
4. `missing`

Generated implementations live under `.supercode/impl` or `.supercode/py_impl`.
Handwritten implementations stay in normal project source directories and are registered through `supercode.toml`.
