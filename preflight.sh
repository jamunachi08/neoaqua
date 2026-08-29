#!/usr/bin/env bash
# Run before pushing to Frappe Cloud. Mirrors what the image build will reject.
set -u
cd "$(dirname "$0")" || exit 1

echo "1/3  merge conflict markers"
if grep -rnE '^(<{7}|={7}|>{7}|\|{7})( |$)' \
     --include='*.py' --include='*.js' --include='*.json' \
     --include='*.md' --include='*.txt' . ; then
  echo "     FOUND - resolve these before pushing"; exit 1
fi
echo "     clean"

echo "2/3  python compiles"
if ! python3 -m compileall -q neoaqua > /dev/null; then
  python3 -m compileall -q neoaqua
  echo "     FAILED"; exit 1
fi
echo "     clean"

echo "3/3  structural guard"
python3 verify_tree.py || exit 1

echo ""
echo "Safe to push."
