#!/usr/bin/env python3
"""verify_tree.py - structural guard for the NeoAqua app.

Run before every commit / Frappe Cloud push:

    python3 verify_tree.py

It fails loudly on the class of mistakes that only surface halfway through a
`bench migrate` on a live site:

  1. every DocType folder has __init__.py, .json and a .py controller
  2. the controller class name matches the DocType name
  3. field_order matches the fields array exactly
  4. Link / Table / Table MultiSelect fields point at a DocType that exists
     (either in this app or in a known Frappe/ERPNext core list)
  5. every dotted path referenced in hooks.py resolves to a real module+attr
  6. every report folder has .json, .py with execute(), and .js filters
  7. no duplicate fieldnames inside a DocType
  8. child tables are declared istable=1 and are not submittable
  9. every Page folder has .json and a .js registering the right page name
 10. no `doc.name = x` on a doctype that autonames from a field
 11. every NeoAqua Settings field referenced in code exists in its JSON
 12. every patches.txt entry is an importable module defining execute()
 13. whitelisted methods that accept dict args also handle JSON strings
 14. no call to an undefined name (the NameError a rename leaves behind)
 15. no unresolved git conflict markers anywhere in the tree
 16. every server method a JS file calls actually exists in Python
 17. Python files parse
"""

import ast
import importlib.util
import json
import os
import re
import sys

APP = "neoaqua"
ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(ROOT, APP)
DOCTYPE_DIR = os.path.join(PKG, APP, "doctype")
REPORT_DIR = os.path.join(PKG, APP, "report")

errors = []
warnings = []

# DocTypes shipped by Frappe / ERPNext that this app links to.
CORE_DOCTYPES = {
	"Account", "Address", "Batch", "Bin", "Company", "Contact", "Cost Center",
	"Customer", "Customer Group", "Delivery Note", "DocType", "Driver",
	"Employee", "Item", "Item Group", "Item Price", "Journal Entry",
	"Material Request", "Mode of Payment", "POS Invoice", "POS Profile",
	"Payment Entry", "Price List", "Purchase Invoice", "Purchase Order",
	"Purchase Receipt", "Quality Inspection", "Role", "Routing", "Sales Invoice",
	"Sales Order", "Sales Person", "Stock Entry", "Supplier", "Territory",
	"UOM", "User", "Warehouse", "Work Order", "Workstation", "Operation", "BOM",
	"Page", "Number Card", "Dashboard Chart", "Sales Taxes and Charges Template",
}


def fail(msg):
	errors.append(msg)


def warn(msg):
	warnings.append(msg)


# ------------------------------------------------------------------ 1-3, 7-8
def collect_doctypes():
	found = {}
	if not os.path.isdir(DOCTYPE_DIR):
		fail(f"missing doctype directory: {DOCTYPE_DIR}")
		return found

	for slug in sorted(os.listdir(DOCTYPE_DIR)):
		d = os.path.join(DOCTYPE_DIR, slug)
		if not os.path.isdir(d) or slug.startswith("_"):
			continue

		jpath = os.path.join(d, f"{slug}.json")
		ppath = os.path.join(d, f"{slug}.py")
		ipath = os.path.join(d, "__init__.py")

		if not os.path.exists(ipath):
			fail(f"[{slug}] missing __init__.py")
		if not os.path.exists(jpath):
			fail(f"[{slug}] missing {slug}.json")
			continue
		if not os.path.exists(ppath):
			fail(f"[{slug}] missing controller {slug}.py")

		with open(jpath) as fh:
			try:
				meta = json.load(fh)
			except json.JSONDecodeError as e:
				fail(f"[{slug}] invalid JSON: {e}")
				continue

		name = meta.get("name")
		found[name] = meta

		# field_order integrity
		fields = [f.get("fieldname") for f in meta.get("fields", [])]
		order = meta.get("field_order", [])
		if order and order != fields:
			fail(f"[{name}] field_order does not match fields array")

		# duplicate fieldnames
		dupes = {f for f in fields if fields.count(f) > 1}
		if dupes:
			fail(f"[{name}] duplicate fieldnames: {sorted(dupes)}")

		# child table sanity
		if meta.get("istable") and meta.get("is_submittable"):
			fail(f"[{name}] a child table must not be submittable")
		if meta.get("istable") and meta.get("permissions"):
			warn(f"[{name}] child table carries permissions rows (harmless, but unused)")

		# controller class name
		if os.path.exists(ppath):
			expected = re.sub(r"\W+", "", (name or "").replace(" ", ""))
			src = open(ppath).read()
			classes = [
				n.name for n in ast.parse(src).body if isinstance(n, ast.ClassDef)
			]
			if expected not in classes:
				fail(f"[{name}] controller class '{expected}' not found (found {classes})")

	return found


# ------------------------------------------------------------------ 4
def check_links(doctypes):
	known = set(doctypes) | CORE_DOCTYPES
	for name, meta in doctypes.items():
		for f in meta.get("fields", []):
			ft = f.get("fieldtype")
			if ft not in ("Link", "Table", "Table MultiSelect"):
				continue
			target = (f.get("options") or "").strip()
			if not target:
				fail(f"[{name}.{f.get('fieldname')}] {ft} field has no options")
				continue
			if target not in known:
				fail(f"[{name}.{f.get('fieldname')}] links to unknown DocType '{target}'")
			if ft in ("Table", "Table MultiSelect"):
				child = doctypes.get(target)
				if child and not child.get("istable"):
					fail(f"[{name}.{f.get('fieldname')}] Table points at non-child DocType '{target}'")

		# fetch_from targets
		fieldnames = {f.get("fieldname") for f in meta.get("fields", [])}
		for f in meta.get("fields", []):
			ff = f.get("fetch_from")
			if not ff:
				continue
			source = ff.split(".")[0]
			if source not in fieldnames:
				fail(f"[{name}.{f.get('fieldname')}] fetch_from source '{source}' is not a field")


# ------------------------------------------------------------------ 5
def check_hooks():
	hooks_path = os.path.join(PKG, "hooks.py")
	if not os.path.exists(hooks_path):
		fail("hooks.py not found")
		return

	src = open(hooks_path).read()
	paths = {
		p
		for p in re.findall(r'"(neoaqua(?:\.[A-Za-z_][A-Za-z0-9_]*)+)"', src)
		if not p.endswith((".js", ".css", ".bundle"))
	}
	for dotted in sorted(paths):
		parts = dotted.split(".")
		# try module.attr, then full module
		for split in (len(parts) - 1, len(parts)):
			module = ".".join(parts[:split])
			attr = parts[split] if split < len(parts) else None
			rel = os.path.join(ROOT, *module.split(".")) + ".py"
			pkg_init = os.path.join(ROOT, *module.split("."), "__init__.py")
			if os.path.exists(rel):
				if attr:
					src_mod = open(rel).read()
					names = _top_level_names(src_mod)
					if attr not in names:
						fail(f"hooks.py -> {dotted}: '{attr}' not defined in {module}")
				break
			if os.path.exists(pkg_init) and attr is None:
				break
		else:
			fail(f"hooks.py -> {dotted}: module not found")


def _top_level_names(src):
	names = set()
	for node in ast.parse(src).body:
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			names.add(node.name)
		elif isinstance(node, ast.Assign):
			for t in node.targets:
				if isinstance(t, ast.Name):
					names.add(t.id)
		elif isinstance(node, (ast.Import, ast.ImportFrom)):
			for a in node.names:
				names.add(a.asname or a.name.split(".")[0])
	return names


# ------------------------------------------------------------------ 6
def check_reports():
	if not os.path.isdir(REPORT_DIR):
		return
	for slug in sorted(os.listdir(REPORT_DIR)):
		d = os.path.join(REPORT_DIR, slug)
		if not os.path.isdir(d) or slug.startswith("_"):
			continue
		for ext in ("json", "py", "js"):
			p = os.path.join(d, f"{slug}.{ext}")
			if not os.path.exists(p):
				fail(f"[report:{slug}] missing {slug}.{ext}")
		py = os.path.join(d, f"{slug}.py")
		if os.path.exists(py):
			names = _top_level_names(open(py).read())
			if "execute" not in names:
				fail(f"[report:{slug}] no execute() entry point")
		js = os.path.join(REPORT_DIR, slug, f"{slug}.js")
		jsonp = os.path.join(REPORT_DIR, slug, f"{slug}.json")
		if os.path.exists(js) and os.path.exists(jsonp):
			report_name = json.load(open(jsonp)).get("report_name")
			if report_name and f'frappe.query_reports["{report_name}"]' not in open(js).read():
				fail(f"[report:{slug}] js key does not match report_name '{report_name}'")


# ------------------------------------------------------------------ 9
def check_pages():
	page_dir = os.path.join(PKG, APP, "page")
	if not os.path.isdir(page_dir):
		return
	for slug in sorted(os.listdir(page_dir)):
		d = os.path.join(page_dir, slug)
		if not os.path.isdir(d) or slug.startswith("_"):
			continue
		for ext in ("json", "js"):
			if not os.path.exists(os.path.join(d, f"{slug}.{ext}")):
				fail(f"[page:{slug}] missing {slug}.{ext}")
		jp = os.path.join(d, f"{slug}.json")
		if os.path.exists(jp):
			meta = json.load(open(jp))
			page_name = meta.get("page_name")
			js = open(os.path.join(d, f"{slug}.js")).read()
			if page_name and f'frappe.pages["{page_name}"]' not in js:
				fail(f"[page:{slug}] js does not register frappe.pages[\"{page_name}\"]")


# Core doctypes whose name is derived from a field, not from doc.name.
# Assigning doc.name before insert() on these is silently discarded.
AUTONAMED_BY_FIELD = {
	"Dashboard Chart": "chart_name",
	"Number Card": "label",
	"Dashboard": "dashboard_name",
	"Workspace": "title",
	"Item Group": "item_group_name",
	"Customer Group": "customer_group_name",
	"Territory": "territory_name",
	"Warehouse": "warehouse_name",
	"Price List": "price_list_name",
	"Mode of Payment": "mode_of_payment",
	"Workstation": "workstation_name",
	"Role": "role_name",
}


def check_autoname_assignments():
	"""Catch `doc.name = x` on a doctype that autonames from a field.

	This is the bug that broke the first Frappe Cloud install: the assignment
	is dropped, the record lands under a different name, and every link to the
	assumed name fails validation at insert time.

	Implemented as a scope walk: inside each function, track which local names
	were bound to frappe.new_doc("X"), then flag any `.name =` on them.
	"""

	def new_doc_target(node):
		"""Return the doctype string if node is frappe.new_doc("X")."""
		if not isinstance(node, ast.Call):
			return None
		fn = node.func
		if not (isinstance(fn, ast.Attribute) and fn.attr in ("new_doc", "get_doc")):
			return None
		if not node.args:
			return None
		arg = node.args[0]
		if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
			return arg.value
		return None

	for base, _dirs, files in os.walk(PKG):
		for f in files:
			if not f.endswith(".py"):
				continue
			path = os.path.join(base, f)
			try:
				tree = ast.parse(open(path).read())
			except SyntaxError:
				continue

			# Only function scopes. Walking the Module as a scope conflates
			# `doc` bindings across unrelated functions and misattributes
			# the doctype.
			for fn in ast.walk(tree):
				if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
					continue

				bound = {}
				for node in ast.walk(fn):
					if isinstance(node, ast.Assign):
						dt = new_doc_target(node.value)
						if dt:
							for t in node.targets:
								if isinstance(t, ast.Name):
									bound[t.id] = dt

				for node in ast.walk(fn):
					if not isinstance(node, ast.Assign):
						continue
					for t in node.targets:
						if not (isinstance(t, ast.Attribute) and t.attr == "name"):
							continue
						if not isinstance(t.value, ast.Name):
							continue
						dt = bound.get(t.value.id)
						if dt and dt in AUTONAMED_BY_FIELD:
							fail(
								f"{os.path.relpath(path, ROOT)}:{node.lineno} assigns "
								f".name on {dt}, which autonames from "
								f"'{AUTONAMED_BY_FIELD[dt]}'. Set that field instead."
							)


CONFLICT_MARKERS = ("<" * 7, "=" * 7, ">" * 7, "|" * 7)


def check_js_method_calls():
	"""Every `method: "neoaqua...."` a JS file calls must exist in Python.

	A frappe.call names its target as a string, so a typo or a Python function
	that never got written is invisible until a user clicks the button and gets
	"module has no attribute". Two of those shipped from silent string-replace
	failures; this makes them a build error instead.
	"""
	pattern = re.compile(r'["\'](' + APP + r'\.[A-Za-z0-9_.]+)["\']')
	for base, dirs, files in os.walk(PKG):
		dirs[:] = [d for d in dirs if d != "node_modules"]
		for f in files:
			if not f.endswith(".js"):
				continue
			path = os.path.join(base, f)
			rel = os.path.relpath(path, ROOT)
			src = open(path, encoding="utf-8", errors="ignore").read()

			for dotted in sorted(set(pattern.findall(src))):
				if dotted.endswith((".js", ".css", ".bundle")):
					continue
				parts = dotted.split(".")[1:]
				if len(parts) < 2:
					continue
				attr = parts[-1]
				module_path = os.path.join(PKG, *parts[:-1]) + ".py"

				if not os.path.exists(module_path):
					# might be a doctype controller method rather than a module path
					continue

				names = _top_level_names(open(module_path).read())
				if attr not in names:
					fail(f"{rel}: calls {dotted}() but "
					     f"{os.path.relpath(module_path, ROOT)} defines no '{attr}'")


def check_merge_conflicts():
	"""Refuse to ship a tree containing git conflict markers.

	An unresolved merge writes `<<<<<<<`, `=======` and `>>>>>>>` into the file
	and git will happily commit them. Python then fails at COMPILE time, which
	on Frappe Cloud means the release is rejected during the image build with
	an "invalid decimal literal" that points at the marker rather than at
	anything you wrote. Catching it here costs a millisecond.
	"""
	exts = (".py", ".js", ".json", ".md", ".txt", ".css", ".html", ".toml")
	for base, dirs, files in os.walk(ROOT):
		dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", "dist")]
		for f in files:
			if not f.endswith(exts):
				continue
			path = os.path.join(base, f)
			try:
				lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
			except OSError:
				continue
			for i, line in enumerate(lines, start=1):
				stripped = line.rstrip()
				for marker in CONFLICT_MARKERS:
					if stripped.startswith(marker) and (
						len(stripped) == len(marker) or stripped[len(marker)] == " "
					):
						fail(
							f"{os.path.relpath(path, ROOT)}:{i} contains an unresolved "
							f"git conflict marker '{marker}' - resolve the merge before pushing"
						)
						break


def check_undefined_names():
	"""Flag calls to names that are not defined anywhere in scope.

	Python only raises NameError when the line actually executes, so a bad
	identifier inside a rarely-hit branch ships happily and detonates on a
	client site. This is what a careless global rename produces: the call site
	is renamed in one function while the definition lives in another.

	Deliberately conservative - it only inspects direct calls to bare names,
	which is where this class of mistake shows up, and treats builtins,
	imports, module-level definitions, parameters, locals, comprehension
	targets, except/with bindings and nested defs as defined.
	"""
	import builtins

	for base, _dirs, files in os.walk(PKG):
		for f in files:
			if not f.endswith(".py"):
				continue
			path = os.path.join(base, f)
			try:
				tree = ast.parse(open(path).read())
			except SyntaxError:
				continue
			rel = os.path.relpath(path, ROOT)

			# MODULE SCOPE ONLY - walking the whole tree would sweep up names
			# defined inside other functions and call them globally visible,
			# which is precisely the mistake this check exists to catch.
			module_names = set(dir(builtins))
			for n in tree.body:
				if isinstance(n, (ast.Import, ast.ImportFrom)):
					for a in n.names:
						module_names.add(a.asname or a.name.split(".")[0])
				elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
					module_names.add(n.name)
				elif isinstance(n, ast.Assign):
					for t in n.targets:
						if isinstance(t, ast.Name):
							module_names.add(t.id)
				elif isinstance(n, ast.If):
					for sub in ast.walk(n):
						if isinstance(sub, (ast.Import, ast.ImportFrom)):
							for a in sub.names:
								module_names.add(a.asname or a.name.split(".")[0])
						elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
							module_names.add(sub.name)
				elif isinstance(n, ast.Try):
					for sub in ast.walk(n):
						if isinstance(sub, (ast.Import, ast.ImportFrom)):
							for a in sub.names:
								module_names.add(a.asname or a.name.split(".")[0])

			for fn in ast.walk(tree):
				if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
					continue

				local = set(module_names)
				args = fn.args
				local |= {a.arg for a in args.args + args.kwonlyargs + args.posonlyargs}
				if args.vararg:
					local.add(args.vararg.arg)
				if args.kwarg:
					local.add(args.kwarg.arg)

				for n in ast.walk(fn):
					if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
						local.add(n.name)
						# a nested def brings its own parameters into scope; we
						# walk the enclosing function as one namespace, so add
						# them here rather than reporting them as undefined
						if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
							na = n.args
							local |= {a.arg for a in na.args + na.kwonlyargs + na.posonlyargs}
							if na.vararg:
								local.add(na.vararg.arg)
							if na.kwarg:
								local.add(na.kwarg.arg)
					elif isinstance(n, ast.Lambda):
						la = n.args
						local |= {a.arg for a in la.args + la.kwonlyargs + la.posonlyargs}
					elif isinstance(n, ast.Assign):
						for t in n.targets:
							for x in ast.walk(t):
								if isinstance(x, ast.Name):
									local.add(x.id)
					elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
						for x in ast.walk(n.target):
							if isinstance(x, ast.Name):
								local.add(x.id)
					elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
						for x in ast.walk(n.target):
							if isinstance(x, ast.Name):
								local.add(x.id)
					elif isinstance(n, ast.ExceptHandler) and n.name:
						local.add(n.name)
					elif isinstance(n, ast.withitem) and n.optional_vars:
						for x in ast.walk(n.optional_vars):
							if isinstance(x, ast.Name):
								local.add(x.id)
					elif isinstance(n, (ast.Global, ast.Nonlocal)):
						local.update(n.names)
					elif isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
						local.add(n.target.id)
					elif isinstance(n, (ast.Import, ast.ImportFrom)):
						for a in n.names:
							local.add(a.asname or a.name.split(".")[0])

				for n in ast.walk(fn):
					if (
						isinstance(n, ast.Call)
						and isinstance(n.func, ast.Name)
						and n.func.id not in local
					):
						fail(f"{rel}:{n.lineno} calls undefined name "
						     f"'{n.func.id}()' in {fn.name}()")


def check_whitelisted_dict_args():
	"""A whitelisted method that branches on `isinstance(x, dict)` must also
	handle the string case.

	`frappe.call` serialises dict arguments to JSON before sending them, so
	server-side the parameter arrives as a str. Code that only tests for dict
	silently takes the else-branch - which is how a JSON payload ended up
	being used as a primary key in the Batch Code Builder.
	"""
	for base, _dirs, files in os.walk(PKG):
		for f in files:
			if not f.endswith(".py"):
				continue
			path = os.path.join(base, f)
			try:
				tree = ast.parse(open(path).read())
			except SyntaxError:
				continue
			rel = os.path.relpath(path, ROOT)

			for fn in ast.walk(tree):
				if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
					continue

				whitelisted = any(
					"whitelist" in ast.dump(dec) for dec in fn.decorator_list
				)
				if not whitelisted:
					continue

				body = ast.dump(fn)
				tests_dict = "'dict'" in body and "isinstance" in body
				if not tests_dict:
					continue

				handles_str = (
					"parse_json" in body
					or "'str'" in body
					or "json.loads" in body
					or "resolve_rule_argument" in body
				)
				if not handles_str:
					fail(
						f"{rel}: whitelisted {fn.name}() branches on isinstance(..., dict) "
						f"but never handles a JSON string - frappe.call sends dicts as strings"
					)


def check_patches():
	"""Every patches.txt entry must be an importable module defining execute().

	Frappe resolves a patch entry as a MODULE PATH and calls `execute()` on it -
	not as module.function. Getting this wrong aborts `bench migrate` partway
	through, after the schema has already been updated. It also catches a name
	existing as both a package directory and a .py module, where the package
	silently wins.
	"""
	txt = os.path.join(PKG, "patches.txt")
	if not os.path.exists(txt):
		return

	for raw in open(txt).read().splitlines():
		line = raw.strip()
		if not line or line.startswith("#") or line.startswith("["):
			continue
		if line.startswith("execute:"):
			continue

		dotted = line.split()[0]
		if not dotted.startswith(f"{APP}."):
			continue

		parts = dotted.split(".")[1:]  # strip the app package
		mod_path = os.path.join(PKG, *parts) + ".py"
		pkg_path = os.path.join(PKG, *parts, "__init__.py")

		if os.path.exists(mod_path) and os.path.exists(os.path.dirname(mod_path) + "/" + parts[-1]):
			fail(f"patches.txt -> {dotted}: exists as BOTH a module and a package; "
			     f"the package wins and the module is unreachable")
			continue

		if not os.path.exists(mod_path):
			if os.path.exists(pkg_path):
				fail(f"patches.txt -> {dotted}: resolves to a package, not a module. "
				     f"A patch must be a .py module defining execute().")
			else:
				fail(f"patches.txt -> {dotted}: no module found at "
				     f"{os.path.relpath(mod_path, ROOT)}")
			continue

		names = _top_level_names(open(mod_path).read())
		if "execute" not in names:
			fail(f"patches.txt -> {dotted}: module defines no execute() function")

	# a version directory that is a package must not also exist as a module
	patches_dir = os.path.join(PKG, "patches")
	if os.path.isdir(patches_dir):
		for entry in os.listdir(patches_dir):
			full = os.path.join(patches_dir, entry)
			if os.path.isdir(full) and os.path.exists(full + ".py"):
				fail(f"patches/{entry} exists as both a package and {entry}.py - "
				     f"remove one, the package always wins")


def check_settings_references():
	"""Every NeoAqua Settings field referenced in code must exist in the JSON.

	A typo here is invisible until runtime, where `settings.foo` silently
	returns None and a control quietly stops working instead of failing.
	"""
	sj = os.path.join(DOCTYPE_DIR, "neoaqua_settings", "neoaqua_settings.json")
	if not os.path.exists(sj):
		return
	fields = {
		f.get("fieldname")
		for f in json.load(open(sj)).get("fields", [])
		if f.get("fieldname")
	}
	safe = {
		"get", "set", "save", "flags", "as_dict", "append", "db_set", "reload",
		"name", "doctype", "meta", "run_method", "insert", "update",
	}

	for base, _dirs, files in os.walk(PKG):
		for f in files:
			if not f.endswith(".py"):
				continue
			path = os.path.join(base, f)
			src = open(path).read()
			rel = os.path.relpath(path, ROOT)

			for m in re.finditer(
				r'get_single_value\(\s*"NeoAqua Settings"\s*,\s*"([a-z_]+)"', src
			):
				if m.group(1) not in fields:
					fail(f"{rel}: NeoAqua Settings has no field '{m.group(1)}' "
					     f"(get_single_value)")

			for m in re.finditer(r"\bsettings\.([a-z_]+)", src):
				fn = m.group(1)
				if fn in safe or fn in fields:
					continue
				fail(f"{rel}: NeoAqua Settings has no field '{fn}' (settings.{fn})")


def check_python_parses():
	for base, _dirs, files in os.walk(PKG):
		for f in files:
			if not f.endswith(".py"):
				continue
			p = os.path.join(base, f)
			try:
				ast.parse(open(p).read())
			except SyntaxError as e:
				fail(f"{os.path.relpath(p, ROOT)}: {e}")


# ------------------------------------------------------------------ main
def main():
	required = [
		os.path.join(PKG, "hooks.py"),
		os.path.join(PKG, "modules.txt"),
		os.path.join(PKG, "patches.txt"),
		os.path.join(PKG, "__init__.py"),
		os.path.join(ROOT, "pyproject.toml"),
	]
	for r in required:
		if not os.path.exists(r):
			fail(f"missing required file: {os.path.relpath(r, ROOT)}")

	doctypes = collect_doctypes()
	check_links(doctypes)
	check_hooks()
	check_reports()
	check_pages()
	check_autoname_assignments()
	check_settings_references()
	check_patches()
	check_whitelisted_dict_args()
	check_undefined_names()
	check_merge_conflicts()
	check_js_method_calls()
	check_python_parses()

	seen = set()
	deduped = []
	for e in errors:
		if e not in seen:
			seen.add(e)
			deduped.append(e)
	errors[:] = deduped

	print(f"NeoAqua verify_tree - {len(doctypes)} doctypes checked")
	for w in dict.fromkeys(warnings):
		print(f"  WARN  {w}")
	if errors:
		print(f"\n{len(errors)} ERROR(S):")
		for e in errors:
			print(f"  FAIL  {e}")
		sys.exit(1)
	print("  OK    structure, links, hooks, reports and syntax all clean")


if __name__ == "__main__":
	main()
