# Recovering the repo after the failed v15.4.0 merge

`main` currently contains unresolved git conflict markers. They are in
`README.md`, `neoaqua/__init__.py` and `neoaqua/setup/dashboards.py` at minimum
— Frappe Cloud only names the first files that fail to compile, so treat the
whole merge as suspect rather than patching the two it mentioned.

The reliable fix is to replace the working tree wholesale. Overwriting resolves
every marker at once, and removing tracked files first means anything deleted
between versions actually leaves the repo instead of lingering.

## Windows / PowerShell

```powershell
# 1. go to your CLONE of the repo (not the extracted zip)
cd E:\path\to\your\neoaqua-clone

# 2. abandon any half-finished merge
git merge --abort 2>$null
git reset --hard HEAD
git pull origin main

# 3. clear the working tree, keeping only .git
Get-ChildItem -Force | Where-Object { $_.Name -ne '.git' } | Remove-Item -Recurse -Force

# 4. copy the new version in (note the trailing \*)
Copy-Item -Path 'E:\neoaqua\neoaqua-v15.4.2\neoaqua\*' -Destination . -Recurse -Force

# 5. prove it is clean BEFORE committing
powershell -ExecutionPolicy Bypass -File .\preflight.ps1

# 6. commit and push
git add -A
git commit -m "NeoAqua v15.4.2 - resolve merge conflict, add preflight guards"
git push origin main
```

Step 5 must print **Safe to push**. If it does not, stop — pushing will just
produce another rejected release.

## Git Bash / macOS / Linux

```bash
cd /path/to/your/neoaqua-clone
git merge --abort 2>/dev/null
git reset --hard HEAD && git pull origin main
find . -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
cp -r /path/to/neoaqua-v15.4.2/neoaqua/. .
./preflight.sh && git add -A \
  && git commit -m "NeoAqua v15.4.2 - resolve merge conflict, add preflight guards" \
  && git push origin main
```

## Then stop it happening again

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

The hook refuses any commit containing conflict markers or non-compiling
Python. Git will otherwise commit `<<<<<<<` into a source file without
complaint, and the first sign of trouble is Frappe Cloud rejecting the release.

## Why merging these drops keeps conflicting

Each release replaces large parts of the same files, so a three-way merge has
plenty to disagree about. Replacing the tree wholesale — as above — has no
conflicts to resolve, because there is no merge. Keep your own changes, if any,
as commits on top of that rather than as edits interleaved with the drop.

## After the push

Frappe Cloud picks up the new commit and builds a release. Then, on the site:

```
bench --site neoaqua.frappe.cloud migrate
bench --site neoaqua.frappe.cloud execute neoaqua.setup.install.repair
```

and check the plant is populated:

```
bench --site neoaqua.frappe.cloud execute neoaqua.setup.orchestrator.print_status
```
