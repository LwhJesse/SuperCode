Experimental AI hole-filling compiler/interpreter frontend.

- Supports C local `super_func`.
- Supports C `super_export_func` with Python `ctypes` binding.
- Supports C `super_struct`.
- Supports C++ `super_class`.
- Supports Python local `sc.super_func`.
- Adds `super init` for clangd / pyright.
- Does not rewrite user source.
- Does not copy full-file shadow source.
- Stores generated implementation units under `.supercode/impl`.
- Experimental; inspect generated code before trusting it.
