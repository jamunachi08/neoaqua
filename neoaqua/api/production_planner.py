# Copyright (c) 2026, Neotec Integrated Solutions
"""Dynamic production planner.

A planner is only as good as the signals it lets you see and switch off. Each
signal here is independently toggleable, because they disagree with each other
and the planner's job is to show the disagreement rather than average it away
silently:

    history       what actually sold over the last N months
    last year     the same calendar window a year ago - the only signal that
                  knows about Ramadan, summer, and school terms
    open orders   demand already committed but not yet delivered
    under production  what is already on the lines and will land in the horizon
    stock         finished goods in the plant and sitting on vans

The arithmetic is deliberately simple enough to argue with:

    forecast      = daily run rate x horizon, optionally blended with last year
                    and multiplied by a seasonality factor
    requirement   = forecast + open orders + safety stock
                    - stock on hand - already in production
    suggested     = requirement, rounded up to a whole BOM batch

Two things a spreadsheet planner usually forgets, and which cost real money:

  * **Capacity.** A suggestion the lines cannot physically run in the horizon is
    not a plan. Required minutes are computed from the BOM routing and compared
    with the workstations' available hours.

  * **Shelf life.** Bottled water expires. Planning ninety days of cover for a
    5-gallon refill with a 180-day life is fine; planning it for a product with
    a 60-day life fills the warehouse with stock that will be written off. The
    planner caps cover at a fraction of remaining shelf life.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate, nowdate

# ---------------------------------------------------------------- seasonality
# Saudi bottled-water demand is strongly seasonal. These are starting points to
# be tuned against the plant's own history, not universal truths - which is why
# seasonality is a toggle and the factors are editable from the UI.
KSA_SEASONALITY = {
	1: 0.85, 2: 0.88, 3: 0.95, 4: 1.05, 5: 1.20, 6: 1.35,
	7: 1.45, 8: 1.45, 9: 1.25, 10: 1.05, 11: 0.92, 12: 0.85,
}


def _f(filters):
	if isinstance(filters, str):
		filters = json.loads(filters)
	return frappe._dict(filters or {})


# ---------------------------------------------------------------- signals
def planned_items(company, item_group=None, production_line=None, include_wip=False):
	"""Items with an active default BOM - the things this plant can make."""
	conditions = ["b.is_active = 1", "b.is_default = 1", "b.docstatus = 1"]
	values = {"company": company}
	conditions.append("b.company = %(company)s")
	if item_group:
		conditions.append("i.item_group = %(item_group)s")
		values["item_group"] = item_group
	if not include_wip:
		conditions.append("i.is_sales_item = 1")

	rows = frappe.db.sql(
		"""
		select i.name as item_code, i.item_name, i.item_group, i.stock_uom,
		       i.shelf_life_in_days, b.name as bom_no, b.quantity as bom_qty
		from `tabBOM` b join `tabItem` i on i.name = b.item
		where {conditions}
		order by i.item_group, i.name
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	if production_line:
		from neoaqua.manufacturing.wo_hooks import LINE_BY_GROUP

		rows = [r for r in rows if LINE_BY_GROUP.get(r.item_group) == production_line]
	return rows


def sales_history(company, items, months):
	"""Monthly sold quantity per item for the trailing N complete months plus
	the current one."""
	if not items:
		return {}, []
	start = get_first_day(add_months(getdate(nowdate()), -months))
	rows = frappe.db.sql(
		"""
		select sii.item_code, date_format(si.posting_date, '%%Y-%%m') as period,
		       sum(sii.stock_qty * if(si.is_return, -1, 1)) as qty
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.company = %(company)s
		  and si.posting_date >= %(start)s and sii.item_code in %(items)s
		group by sii.item_code, period
		""",
		{"company": company, "start": start, "items": items},
		as_dict=True,
	)
	out = defaultdict(dict)
	periods = set()
	for r in rows:
		out[r.item_code][r.period] = flt(r.qty)
		periods.add(r.period)
	return out, sorted(periods)


def last_year_window(company, items, from_date, to_date):
	if not items:
		return {}
	rows = frappe.db.sql(
		"""
		select sii.item_code, sum(sii.stock_qty * if(si.is_return, -1, 1)) as qty
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.company = %(company)s
		  and si.posting_date between %(start)s and %(end)s
		  and sii.item_code in %(items)s
		group by sii.item_code
		""",
		{
			"company": company,
			"start": add_months(getdate(from_date), -12),
			"end": add_months(getdate(to_date), -12),
			"items": items,
		},
		as_dict=True,
	)
	return {r.item_code: flt(r.qty) for r in rows}


def open_sales_orders(company, items):
	if not items:
		return {}
	rows = frappe.db.sql(
		"""
		select soi.item_code, sum(soi.stock_qty - soi.delivered_qty) as qty
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		where so.docstatus = 1 and so.company = %(company)s
		  and so.status not in ('Closed', 'Completed', 'Cancelled')
		  and soi.item_code in %(items)s
		group by soi.item_code
		""",
		{"company": company, "items": items},
		as_dict=True,
	)
	return {r.item_code: max(flt(r.qty), 0) for r in rows}


def under_production(company, items):
	"""Quantity on submitted work orders that has not yet been produced."""
	if not items:
		return {}
	rows = frappe.db.sql(
		"""
		select production_item as item_code, sum(qty - produced_qty) as qty
		from `tabWork Order`
		where docstatus = 1 and company = %(company)s
		  and status not in ('Completed', 'Stopped', 'Closed')
		  and production_item in %(items)s
		group by production_item
		""",
		{"company": company, "items": items},
		as_dict=True,
	)
	return {r.item_code: max(flt(r.qty), 0) for r in rows}


def stock_position(company, items):
	"""Finished goods split between the plant and the vans, because stock on a
	van is committed to a route and is not freely available to another."""
	if not items:
		return {}, {}
	van_warehouses = frappe.get_all("Van", filters={"status": "Active"}, pluck="warehouse")
	rows = frappe.db.sql(
		"""select item_code, warehouse, sum(actual_qty) as qty
		   from `tabBin` where item_code in %(items)s group by item_code, warehouse""",
		{"items": items},
		as_dict=True,
	)
	plant, van = defaultdict(float), defaultdict(float)
	for r in rows:
		if r.warehouse in van_warehouses:
			van[r.item_code] += flt(r.qty)
		else:
			plant[r.item_code] += flt(r.qty)
	return plant, van


# ---------------------------------------------------------------- capacity
def line_capacity(company, horizon_days):
	"""Available minutes per production line over the horizon."""
	from neoaqua.manufacturing.wo_hooks import LINE_BY_GROUP

	line_ws = {
		"Line 1 - Small PET": ["Filling Line 1 - Small PET"],
		"Line 2 - Large PET": ["Filling Line 2 - Large PET"],
		"Line 3 - 5 Gallon": ["Filling Line 3 - 5 Gallon"],
		"RO Plant": ["RO Treatment Plant", "Ozonation & Storage"],
	}
	hours_per_day = flt(
		frappe.db.get_single_value("NeoAqua Settings", "planning_hours_per_day")
	) or 16.0
	working_days = max(int(horizon_days * 6 / 7), 1)  # one rest day a week

	return {
		line: {
			"workstations": ws,
			"available_minutes": hours_per_day * 60 * working_days * len(ws),
		}
		for line, ws in line_ws.items()
	}


def bom_minutes(bom_no, bom_qty):
	"""Routing minutes per unit for this BOM."""
	total = flt(
		frappe.db.sql(
			"select sum(time_in_mins) from `tabBOM Operation` where parent = %s", bom_no
		)[0][0]
	)
	return (total / flt(bom_qty)) if flt(bom_qty) else 0


# ---------------------------------------------------------------- shortfall
def material_shortfall(rows, company):
	"""Explode the suggested quantities through the BOM tree and compare the
	raw-material requirement with what is in stock.

	This is the step that turns a production plan into a purchasing decision -
	a plan that cannot be fed is a wish."""
	required = defaultdict(float)

	for r in rows:
		qty = flt(r.get("suggested_qty"))
		if qty <= 0 or not r.get("bom_no"):
			continue
		try:
			from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict

			items = get_bom_items_as_dict(
				r["bom_no"], company, qty=qty, fetch_exploded=1, fetch_scrap_items=0
			)
			for code, d in items.items():
				required[code] += flt(d.get("qty"))
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua planner: explode {r.get('bom_no')}")

	if not required:
		return []

	codes = list(required)
	stock = defaultdict(float)
	for b in frappe.db.sql(
		"""select item_code, sum(actual_qty) as qty from `tabBin`
		   where item_code in %(c)s group by item_code""",
		{"c": codes}, as_dict=True,
	):
		stock[b.item_code] = flt(b.qty)

	on_order = defaultdict(float)
	for p in frappe.db.sql(
		"""select poi.item_code, sum(poi.stock_qty - poi.received_qty) as qty
		   from `tabPurchase Order Item` poi
		   join `tabPurchase Order` po on po.name = poi.parent
		   where po.docstatus = 1 and po.status not in ('Closed','Completed')
		     and poi.item_code in %(c)s group by poi.item_code""",
		{"c": codes}, as_dict=True,
	):
		on_order[p.item_code] = max(flt(p.qty), 0)

	out = []
	meta = {
		i.name: i
		for i in frappe.get_all(
			"Item", filters={"name": ["in", codes]},
			fields=["name", "item_name", "stock_uom", "is_purchase_item"],
		)
	}
	for code, req in sorted(required.items(), key=lambda kv: -kv[1]):
		have = stock.get(code, 0)
		ordered = on_order.get(code, 0)
		short = req - have - ordered
		m = meta.get(code) or frappe._dict()
		out.append(
			{
				"item_code": code,
				"item_name": m.get("item_name"),
				"uom": m.get("stock_uom"),
				"required": req,
				"in_stock": have,
				"on_order": ordered,
				"shortfall": max(short, 0),
				"purchasable": bool(m.get("is_purchase_item")),
			}
		)
	return out


# ---------------------------------------------------------------- the plan
@frappe.whitelist()
def get_plan(filters=None):
	f = _f(filters)
	company = f.get("company") or frappe.defaults.get_user_default("company")
	if not company:
		frappe.throw(_("Select a Company."))

	horizon_days = cint(f.get("horizon_days")) or 30
	history_months = cint(f.get("history_months")) or 3
	safety_days = cint(f.get("safety_days")) or 7
	from_date = getdate(f.get("from_date") or nowdate())
	to_date = getdate(f.get("to_date") or add_days(from_date, horizon_days))
	horizon_days = max((to_date - from_date).days, 1)

	show = {
		"history": cint(f.get("show_history", 1)),
		"last_year": cint(f.get("show_last_year", 0)),
		"open_orders": cint(f.get("show_open_orders", 1)),
		"wip": cint(f.get("show_wip", 1)),
		"stock": cint(f.get("show_stock", 1)),
		"seasonality": cint(f.get("apply_seasonality", 0)),
		"capacity": cint(f.get("show_capacity", 1)),
	}

	catalogue = planned_items(
		company, f.get("item_group"), f.get("production_line"), cint(f.get("include_sub_assemblies"))
	)
	items = [c.item_code for c in catalogue]
	if not items:
		return {"rows": [], "periods": [], "message": _("No items with an active BOM match these filters.")}

	history, periods = sales_history(company, items, history_months) if show["history"] else ({}, [])
	ly = last_year_window(company, items, from_date, to_date) if show["last_year"] else {}
	orders = open_sales_orders(company, items) if show["open_orders"] else {}
	wip = under_production(company, items) if show["wip"] else {}
	plant_stock, van_stock = stock_position(company, items) if show["stock"] else ({}, {})

	season = KSA_SEASONALITY.get(from_date.month, 1.0) if show["seasonality"] else 1.0
	history_days = max(history_months * 30, 1)

	from neoaqua.manufacturing.wo_hooks import LINE_BY_GROUP

	rows = []
	for c in catalogue:
		hist = history.get(c.item_code, {})
		hist_total = sum(hist.values())
		daily = hist_total / history_days if history_days else 0
		base_forecast = daily * horizon_days

		ly_qty = flt(ly.get(c.item_code))
		if show["last_year"] and ly_qty > 0:
			# Blend the two signals rather than trusting either alone: recent
			# behaviour knows about this year's customers, last year knows
			# about the season.
			forecast = base_forecast * 0.6 + ly_qty * 0.4
			signal = "history + last year"
		else:
			forecast = base_forecast
			signal = "history"

		forecast *= season

		safety = daily * safety_days * season
		on_hand = flt(plant_stock.get(c.item_code)) + flt(van_stock.get(c.item_code))
		committed = flt(orders.get(c.item_code))
		in_production = flt(wip.get(c.item_code))

		requirement = forecast + committed + safety - on_hand - in_production
		suggested = max(requirement, 0)

		# shelf-life guard
		capped_by_shelf_life = False
		shelf = cint(c.shelf_life_in_days)
		if shelf and daily > 0:
			max_cover_days = shelf * 0.5
			max_qty = daily * max_cover_days - on_hand
			if suggested > max_qty > 0:
				suggested = max_qty
				capped_by_shelf_life = True

		if cint(f.get("round_to_batch", 1)) and flt(c.bom_qty) > 0 and suggested > 0:
			batches = -(-suggested // flt(c.bom_qty))  # ceiling division
			suggested = batches * flt(c.bom_qty)

		line = LINE_BY_GROUP.get(c.item_group)
		minutes = bom_minutes(c.bom_no, c.bom_qty) * suggested if show["capacity"] else 0

		rows.append(
			{
				"item_code": c.item_code,
				"item_name": c.item_name,
				"item_group": c.item_group,
				"uom": c.stock_uom,
				"bom_no": c.bom_no,
				"bom_qty": flt(c.bom_qty),
				"production_line": line,
				"history": {p: flt(hist.get(p, 0)) for p in periods},
				"history_total": hist_total,
				"avg_monthly": hist_total / history_months if history_months else 0,
				"avg_daily": daily,
				"last_year": ly_qty,
				"yoy_pct": ((hist_total - ly_qty) / ly_qty * 100) if ly_qty else None,
				"open_orders": committed,
				"under_production": in_production,
				"stock_plant": flt(plant_stock.get(c.item_code)),
				"stock_van": flt(van_stock.get(c.item_code)),
				"stock_total": on_hand,
				"forecast": forecast,
				"safety_stock": safety,
				"requirement": requirement,
				"suggested_qty": round(suggested, 2),
				"days_cover_after": ((on_hand + suggested) / daily) if daily else None,
				"signal": signal,
				"capped_by_shelf_life": capped_by_shelf_life,
				"minutes": minutes,
			}
		)

	rows.sort(key=lambda r: r["suggested_qty"], reverse=True)

	capacity = []
	if show["capacity"]:
		avail = line_capacity(company, horizon_days)
		used = defaultdict(float)
		for r in rows:
			if r["production_line"]:
				used[r["production_line"]] += r["minutes"]
		for line, info in avail.items():
			need = used.get(line, 0)
			capacity.append(
				{
					"line": line,
					"required_hours": round(need / 60, 1),
					"available_hours": round(info["available_minutes"] / 60, 1),
					"utilisation": (need / info["available_minutes"] * 100)
					if info["available_minutes"] else 0,
				}
			)

	return {
		"company": company,
		"from_date": str(from_date),
		"to_date": str(to_date),
		"horizon_days": horizon_days,
		"periods": periods,
		"season_factor": season,
		"season_month": from_date.strftime("%B"),
		"show": show,
		"rows": rows,
		"capacity": capacity,
		"totals": {
			"items": len(rows),
			"to_produce": sum(r["suggested_qty"] for r in rows),
			"open_orders": sum(r["open_orders"] for r in rows),
			"under_production": sum(r["under_production"] for r in rows),
			"stock_total": sum(r["stock_total"] for r in rows),
		},
	}


@frappe.whitelist()
def get_shortfall(rows, company=None):
	company = company or frappe.defaults.get_user_default("company")
	rows = json.loads(rows) if isinstance(rows, str) else rows
	return material_shortfall(rows, company)


# ---------------------------------------------------------------- actions
@frappe.whitelist()
def create_production_plan(rows, company=None, from_date=None, to_date=None):
	"""Create a DRAFT Production Plan from the suggested quantities.

	Draft, deliberately. The planner proposes; a person decides."""
	rows = json.loads(rows) if isinstance(rows, str) else rows
	rows = [r for r in rows if flt(r.get("suggested_qty")) > 0]
	if not rows:
		frappe.throw(_("Nothing to plan — every suggested quantity is zero."))

	company = company or frappe.defaults.get_user_default("company")
	settings = frappe.get_cached_doc("NeoAqua Settings")

	pp = frappe.new_doc("Production Plan")
	pp.update(
		{
			"company": company,
			"posting_date": nowdate(),
			"get_items_from": "",
			"for_warehouse": settings.default_plant_warehouse,
		}
	)
	for r in rows:
		pp.append(
			"po_items",
			{
				"item_code": r["item_code"],
				"bom_no": r.get("bom_no"),
				"planned_qty": flt(r["suggested_qty"]),
				"planned_start_date": from_date or nowdate(),
				"warehouse": settings.default_plant_warehouse,
				"stock_uom": r.get("uom"),
			},
		)
	pp.flags.ignore_permissions = True
	pp.flags.ignore_mandatory = True
	pp.insert()
	return {"production_plan": pp.name, "items": len(rows)}


@frappe.whitelist()
def create_material_requests(shortfall, company=None, schedule_date=None):
	"""Raise a draft Material Request for the raw materials the plan is short of."""
	shortfall = json.loads(shortfall) if isinstance(shortfall, str) else shortfall
	lines = [s for s in shortfall if flt(s.get("shortfall")) > 0 and s.get("purchasable")]
	if not lines:
		frappe.throw(_("No purchasable shortfall to request."))

	company = company or frappe.defaults.get_user_default("company")
	settings = frappe.get_cached_doc("NeoAqua Settings")
	schedule_date = schedule_date or add_days(nowdate(), 7)

	mr = frappe.new_doc("Material Request")
	mr.update(
		{
			"material_request_type": "Purchase",
			"company": company,
			"transaction_date": nowdate(),
			"schedule_date": schedule_date,
		}
	)
	for s in lines:
		mr.append(
			"items",
			{
				"item_code": s["item_code"],
				"qty": flt(s["shortfall"]),
				"warehouse": settings.rm_warehouse or settings.default_plant_warehouse,
				"schedule_date": schedule_date,
			},
		)
	mr.flags.ignore_permissions = True
	mr.flags.ignore_mandatory = True
	mr.insert()
	return {"material_request": mr.name, "items": len(lines)}
