# Copyright (c) 2026, Neotec Integrated Solutions
"""v15.1.1 - repair dashboard artifacts left mis-named by earlier installers.

Dashboard Chart autonames from `chart_name` and Number Card from `label`, so
the 15.0.0 installer's `doc.name = ...` was discarded and those records landed
under their short labels, leaving the dashboards unable to link. This rebuilds
them against whatever names actually exist.
"""

import frappe

from neoaqua.setup import dashboards


def execute():
	try:
		dashboards.run()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "NeoAqua v15.1.1 dashboard rebuild")
