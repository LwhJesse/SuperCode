#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
HOST_PYTHON=$(command -v python3)

if ! command -v docker >/dev/null 2>&1 && ! command -v podman >/dev/null 2>&1; then
  echo "Docker/podman not available; skipped clean environment check."
  exit 0
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

python3 -m venv "$TMPDIR/venv"
. "$TMPDIR/venv/bin/activate"
"$HOST_PYTHON" -m build --wheel --no-isolation "$ROOT_DIR" >/dev/null
python -m pip install --no-deps "$ROOT_DIR"/dist/*.whl >/dev/null

cd "$ROOT_DIR"
super --help >/dev/null
super init --force >/dev/null

cat > "$TMPDIR/plain.c" <<'EOF'
#include <stdio.h>
int main(void) { puts("plain"); return 0; }
EOF
super "$TMPDIR/plain.c" -o "$TMPDIR/plain"
"$TMPDIR/plain" | grep '^plain$' >/dev/null

cat > "$TMPDIR/plain.py" <<'EOF'
print("plain")
EOF
super "$TMPDIR/plain.py" | grep 'plain' >/dev/null

super examples/c_local_func/main.c -o "$TMPDIR/sc-local" --mock >/dev/null
"$TMPDIR/sc-local" | grep '^1$' >/dev/null

super examples/python_local_func/main.py --mock | grep '^1$' >/dev/null

INSTALLED_INCLUDE_DIR=$("$TMPDIR/venv/bin/python" -c 'from supercode.paths import get_packaged_include_dir; print(get_packaged_include_dir().resolve())')
grep "$INSTALLED_INCLUDE_DIR" .clangd >/dev/null

if grep -R "return super_func" .supercode/impl 2>/dev/null; then
  echo "Generated impl unexpectedly copied source line"
  exit 1
fi

echo "Clean environment check passed."
