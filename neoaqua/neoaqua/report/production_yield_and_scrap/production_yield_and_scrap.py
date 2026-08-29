# Copyright (c) 2026, Neotec Integrated Solutions
"""Work-order level yield: planned vs produced, material variance and scrap."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"label": _("Work Order"), "fieldname": "name", "fieldtype": "Link", "options": "Work Order", "width": 140},
		{"label": _("Item"), "fieldname": "production_item", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Line"), "fieldname": "neoaqua_production_line", "fieldtype": "Data", "width": 140},
		{"label": _("Planned Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 110},
		{"label": _("Produced Qty"), "fieldname": "produced_qty", "fieldtype": "Float", "width": 115},
		{"label": _("Yield %"), "fieldname": "yield_pct", "fieldtype": "Percent", "width": 90},
		{"label": _("Planned Cost"), "fieldname": "planned_cost", "fieldtype": "Currency", "width": 125},
		{"label": _("Actual Cost"), "fieldname": "actual_cost", "fieldtype": "Currency", "width": 125},
		{"label": _("Cost Variance"), "fieldname": "cost_variance", "fieldtype": "Currency", "width": 125},
		{"label": _("Cost / Unit"), "fieldname": "cost_per_unit", "fieldtype": "Currency", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	conditions = ["wo.docstatus = 1"]
	values = {}
	if filters.get("from_date"):
		conditions.append("wo.creation >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("wo.creation <= %(to_date)s")
		values["to_date"] = filters.to_date
	for f, col in (("production_line", "neoaqua_production_line"), ("item", "production_item"), ("company", "company")):
		if filters.get(f):
			conditions.append(f"wo.{col} = %({f})s")
			values[f] = filters.get(f)

	rows = frappe.db.sql(
		"""
		select wo.name, wo.production_item, wo.item_name, wo.neoaqua_production_line,
		       wo.qty, wo.produced_qty, wo.status,
		       wo.planned_operating_cost, wo.total_operating_cost,
		       bom.total_cost as bom_cost, bom.quantity as bom_qty
		from `tabWork Order` wo
		left join `tabBOM` bom on bom.name = wo.bom_no
		where {conditions}
		order by wo.creation desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	for r in rows:
		unit_bom_cost = flt(r.bom_cost) / flt(r.bom_qty) if flt(r.bom_qty) else 0
		r["yield_pct"] = (flt(r.produced_qty) / flt(r.qty) * 100) if flt(r.qty) else 0
		r["planned_cost"] = unit_bom_cost * flt(r.qty) + flt(r.planned_operating_cost)
		r["actual_cost"] = unit_bom_cost * flt(r.produced_qty) + flt(r.total_operating_cost)
		r["cost_variance"] = flt(r["actual_cost"]) - flt(r["planned_cost"])
		r["cost_per_unit"] = flt(r["actual_cost"]) / flt(r.produced_qty) if flt(r.produced_qty) else 0
	return rows


def get_chart(data):
	by_line = {}
	for d in data:
		line = d.get("neoaqua_production_line") or _("Unassigned")
		by_line.setdefault(line, [0, 0])
		by_line[line][0] += flt(d.get("qty"))
		by_line[line][1] += flt(d.get("produced_qty"))
	labels = list(by_line)
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Planned"), "values": [by_line[k][0] for k in labels]},
				{"name": _("Produced"), "values": [by_line[k][1] for k in labels]},
			],
		},
		"type": "bar",
	}


def get_summary(data):
	planned = sum(flt(d.get("qty")) for d in data)
	produced = sum(flt(d.get("produced_qty")) for d in data)
	return [
		{"label": _("Planned Qty"), "value": planned, "datatype": "Float"},
		{"label": _("Produced Qty"), "value": produced, "datatype": "Float"},
		{"label": _("Overall Yield"), "value": (produced / planned * 100) if planned else 0, "datatype": "Percent",
		 "indicator": "Green" if planned and produced / planned > 0.97 else "Orange"},
		{"label": _("Cost Variance"), "value": sum(flt(d.get("cost_variance")) for d in data), "datatype": "Currency"},
	]
