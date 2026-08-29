# Copyright (c) 2026, Neotec Integrated Solutions
"""Demo data generator.

Produces one coherent week of trading so a fresh site can be explored end to
end rather than stared at empty:

    parties      4 suppliers with SFDA/CR compliance data, 10 customers across
                 every channel, 3 salesmen with geofenced routes
    procurement  material request -> purchase order -> receipt -> invoice
    production   a five-level run: RO permeate -> ozonated water -> blown
                 bottle -> filled bottle -> shrink pack, with batches and
                 quality checks at each gate
    distribution 3 van trips with GPS check-ins, POS invoices, collections,
                 container movements and a settled day close

EVERY document created is written to `NeoAqua Demo Record` with a monotonic
sequence number. That log is what makes deletion safe: the cleanup walks it in
reverse, so dependents are always removed before the things they depend on,
and nothing outside the log is ever touched.
"""

import json
import random

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate, random_string

SEQ = {"n": 0}
RUN = {"id": None}


# ================================================================== tracking
def start_run():
	RUN["id"] = f"DEMO-{random_string(8).upper()}"
	SEQ["n"] = 0
	return RUN["id"]


def track(doc, is_master=0):
	"""Log a created document so cleanup can find it later."""
	SEQ["n"] += 1
	rec = frappe.new_doc("NeoAqua Demo Record")
	rec.update(
		{
			"run_id": RUN["id"],
			"sequence": SEQ["n"],
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"is_master": is_master,
			"is_submittable": 1 if doc.meta.is_submittable else 0,
			"status": "Created",
		}
	)
	rec.flags.ignore_permissions = True
	rec.insert()
	return doc


def _new(doctype, values, submit=False, is_master=0, before_submit=None):
	"""Create a document, optionally adjust it after insert, then submit.

	`before_submit` exists because some child rows are only populated by the
	controller's own validate() - quality parameters being the example - so
	they cannot be supplied up front.
	"""
	doc = frappe.new_doc(doctype)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	if before_submit:
		before_submit(doc)
		doc.save()
	if submit:
		doc.submit()
	track(doc, is_master)
	return doc


def abbr(company):
	return frappe.get_cached_value("Company", company, "abbr")


# ================================================================== parties
SUPPLIERS = [
	("Gulf Preform Industries", "Preforms & Closures", "SFDA-PRF-88214", "1010445721"),
	("Riyadh Closure Manufacturing", "Preforms & Closures", "SFDA-CAP-44190", "1010337812"),
	("Arabian Label & Print", "Labels & Secondary Packaging", "SFDA-LBL-77502", "1010229945"),
	("Nahdi Water Treatment Chemicals", "Treatment Chemicals", "SFDA-CHM-31088", "2050118834"),
]

CUSTOMERS = [
	# name, group, territory, lat, lng, credit_limit
	("Al Othaim Markets - Exit 9", "Supermarket Chain", "Riyadh - East", 24.7912, 46.7620, 250000),
	("Panda Hypermarket - Malaz", "Supermarket Chain", "Riyadh - South", 24.6580, 46.7320, 250000),
	("Baqala Al Noor", "Retail Baqala", "Riyadh - North", 24.7743, 46.6885, 15000),
	("Baqala Al Rayyan", "Retail Baqala", "Riyadh - North", 24.7891, 46.6702, 15000),
	("Baqala Al Salam", "Retail Baqala", "Riyadh - South", 24.6321, 46.7104, 12000),
	("Najd Catering Services", "HORECA", "Riyadh - East", 24.8102, 46.7455, 80000),
	("Marriott Riyadh - Banquet", "HORECA", "Riyadh - North", 24.7620, 46.6519, 120000),
	("Al Faisaliah Offices HOD", "Home & Office Delivery", "Riyadh - North", 24.6905, 46.6849, 40000),
	("Kingdom Tower Facilities", "Home & Office Delivery", "Riyadh - North", 24.7115, 46.6743, 60000),
	("Wholesale Depot Al Kharj Rd", "Wholesale Distributor", "Riyadh - East", 24.7280, 46.8210, 400000),
]

SALESMEN = [
	("Fahad Al Qahtani", "Van 01", "Riyadh - North Route"),
	("Mohammed Al Harbi", "Van 02", "Riyadh - South Route"),
	("Sultan Al Dosari", "Van 03", "Riyadh - East Route"),
]


def create_suppliers(company):
	out = []
	for name, group, sfda, cr in SUPPLIERS:
		if frappe.db.exists("Supplier", name):
			out.append(name)
			continue
		doc = _new(
			"Supplier",
			{
				"supplier_name": name,
				"supplier_group": frappe.db.get_value("Supplier Group", {"name": "Raw Material"}, "name")
				or "All Supplier Groups",
				"country": "Saudi Arabia",
				"default_currency": "SAR",
				"neoaqua_sfda_registration": sfda,
				"neoaqua_cr_number": cr,
				"neoaqua_cr_expiry": add_days(nowdate(), 400),
				"neoaqua_supplier_rating": "A - Approved",
			},
			is_master=1,
		)
		out.append(doc.name)
	return out


def create_customers(company):
	out = []
	for name, group, territory, lat, lng, limit in CUSTOMERS:
		if frappe.db.exists("Customer", name):
			out.append(name)
			continue

		zone = None
		if not frappe.db.exists("Geofence Zone", f"{name} Zone"):
			z = _new(
				"Geofence Zone",
				{
					"zone_name": f"{name} Zone",
					"zone_type": "Circle",
					"company": company,
					"is_active": 1,
					"center_latitude": lat,
					"center_longitude": lng,
					"radius_m": 150,
					"address_line": f"{territory}, Riyadh",
				},
				is_master=1,
			)
			zone = z.name

		price_list = {
			"Wholesale Distributor": "NeoAqua Wholesale",
			"Supermarket Chain": "NeoAqua Wholesale",
			"HORECA": "NeoAqua HORECA",
		}.get(group, "NeoAqua Retail")

		doc = _new(
			"Customer",
			{
				"customer_name": name,
				"customer_group": group if frappe.db.exists("Customer Group", group) else "All Customer Groups",
				"territory": territory if frappe.db.exists("Territory", territory) else "All Territories",
				"customer_type": "Company",
				"default_currency": "SAR",
				"default_price_list": price_list if frappe.db.exists("Price List", price_list) else None,
				"credit_limits": [{"company": company, "credit_limit": limit}],
				"neoaqua_geofence_zone": zone,
				"neoaqua_visit_frequency": "Alternate Day" if group == "Retail Baqala" else "Weekly",
			},
			is_master=1,
		)
		if zone:
			frappe.db.set_value("Geofence Zone", zone, "customer", doc.name, update_modified=False)
		out.append(doc.name)
	return out


def create_salesmen(company, customers):
	"""Sales Person records plus route stops, so trips have somewhere to go."""
	out = []
	for idx, (name, van, route) in enumerate(SALESMEN):
		if not frappe.db.exists("Sales Person", name):
			_new(
				"Sales Person",
				{
					"sales_person_name": name,
					"parent_sales_person": frappe.db.get_value(
						"Sales Person", {"is_group": 1}, "name"
					),
					"is_group": 0,
					"enabled": 1,
				},
				is_master=1,
			)
		out.append(name)

		if frappe.db.exists("Van", van):
			frappe.db.set_value("Van", van, "salesman", name, update_modified=False)

		if frappe.db.exists("Van Route", route):
			doc = frappe.get_doc("Van Route", route)
			if not doc.stops:
				chunk = customers[idx::3] or customers[:3]
				for seq, cust in enumerate(chunk, start=1):
					doc.append(
						"stops",
						{
							"customer": cust,
							"sequence": seq,
							"visit_days": "Sun,Tue,Thu",
							"geofence_zone": frappe.db.get_value(
								"Customer", cust, "neoaqua_geofence_zone"
							),
						},
					)
			doc.salesman = name
			doc.van = van if frappe.db.exists("Van", van) else None
			doc.flags.ignore_permissions = True
			doc.save()
	return out


# ================================================================== stock
RM_OPENING = [
	("RM-PRF-09G", 60000), ("RM-PRF-11G", 40000), ("RM-PRF-14G", 120000),
	("RM-PRF-28G", 30000), ("RM-PRF-60G", 12000),
	("RM-CAP-28", 220000), ("RM-CAP-30", 15000), ("RM-CAP-55", 6000),
	("RM-HDL-5L", 12000),
	("RM-LBL-200", 60000), ("RM-LBL-330", 40000), ("RM-LBL-600", 120000),
	("RM-LBL-1500", 30000), ("RM-LBL-5000", 12000), ("RM-LBL-189", 6000),
	("RM-SHR-FILM", 900), ("RM-CTN-TRAY", 9000), ("RM-STRETCH", 200),
	("RM-WTR-SRC", 500000),
	("RM-CHM-ANTISCAL", 60), ("RM-CHM-NAOCL", 220), ("RM-CHM-MINERAL", 90),
	("RM-CHM-CIP", 150),
	("RM-BTL-PC-189", 3000),
]


def create_opening_stock(company, posting_date):
	"""A Material Receipt so production has something to consume. With
	perpetual inventory on, this debits the stock accounts and credits stock
	adjustment, which is exactly how an opening balance should land."""
	a = abbr(company)
	warehouse = f"Raw Material Store - {a}"
	if not frappe.db.exists("Warehouse", warehouse):
		return None

	items = []
	for code, qty in RM_OPENING:
		if not frappe.db.exists("Item", code):
			continue
		rate = flt(frappe.db.get_value("Item", code, "valuation_rate")) or 1
		items.append({"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": rate})

	if not items:
		return None

	return _new(
		"Stock Entry",
		{
			"stock_entry_type": "Material Receipt",
			"company": company,
			"posting_date": posting_date,
			"set_posting_time": 1,
			"items": items,
			"remarks": "NeoAqua demo - opening raw material stock",
		},
		submit=True,
	)


# ================================================================== p2p
def run_procurement(company, posting_date, suppliers):
	"""Material Request -> Purchase Order -> Purchase Receipt -> Purchase
	Invoice, exercising the SFDA and CoA gates on the way through."""
	a = abbr(company)
	warehouse = f"Raw Material Store - {a}"
	created = {}

	lines = [
		("RM-PRF-14G", 50000, suppliers[0]),
		("RM-CAP-28", 60000, suppliers[1]),
		("RM-LBL-600", 50000, suppliers[2]),
		("RM-CHM-MINERAL", 25, suppliers[3]),
	]

	mr_items = []
	for code, qty, _sup in lines:
		if frappe.db.exists("Item", code):
			mr_items.append(
				{"item_code": code, "qty": qty, "warehouse": warehouse, "schedule_date": add_days(posting_date, 5)}
			)
	if not mr_items:
		return created

	mr = _new(
		"Material Request",
		{
			"material_request_type": "Purchase",
			"company": company,
			"transaction_date": posting_date,
			"schedule_date": add_days(posting_date, 5),
			"items": mr_items,
		},
		submit=True,
	)
	created["material_request"] = mr.name

	# one purchase order per supplier so the compliance gate is exercised
	by_supplier = {}
	for code, qty, sup in lines:
		if frappe.db.exists("Item", code):
			by_supplier.setdefault(sup, []).append((code, qty))

	created["purchase_orders"] = []
	for supplier, rows in by_supplier.items():
		po = _new(
			"Purchase Order",
			{
				"supplier": supplier,
				"company": company,
				"transaction_date": posting_date,
				"schedule_date": add_days(posting_date, 5),
				"currency": "SAR",
				"conversion_rate": 1,
				"items": [
					{
						"item_code": code,
						"qty": qty,
						"warehouse": warehouse,
						"schedule_date": add_days(posting_date, 5),
						"rate": flt(frappe.db.get_value("Item", code, "valuation_rate")),
					}
					for code, qty in rows
				],
			},
			submit=True,
		)
		created["purchase_orders"].append(po.name)

		try:
			from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

			pr = make_purchase_receipt(po.name)
			pr.posting_date = add_days(posting_date, 2)
			pr.set_posting_time = 1
			pr.neoaqua_coa_reference = f"COA-{random_string(6).upper()}"
			pr.flags.ignore_permissions = True
			pr.flags.ignore_mandatory = True
			pr.insert()
			pr.submit()
			track(pr)
			created.setdefault("purchase_receipts", []).append(pr.name)

			from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

			pi = make_purchase_invoice(pr.name)
			pi.posting_date = add_days(posting_date, 3)
			pi.set_posting_time = 1
			pi.bill_no = f"INV-{random_string(6).upper()}"
			pi.bill_date = add_days(posting_date, 2)
			pi.flags.ignore_permissions = True
			pi.flags.ignore_mandatory = True
			pi.insert()
			pi.submit()
			track(pi)
			created.setdefault("purchase_invoices", []).append(pi.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: P2P for {supplier}")

	return created


# ================================================================== production
def fill_quality_parameters(qc_doc):
	"""Populate the parameter panel the controller loaded on insert, with
	readings comfortably inside spec so the batch releases."""
	for row in qc_doc.parameters:
		lo, hi = flt(row.min_value), flt(row.max_value)
		if lo == hi:
			row.observed_value = lo
		else:
			row.observed_value = round(lo + (hi - lo) * random.uniform(0.35, 0.65), 3)


PRODUCTION_CHAIN = [
	("WIP-WTR-RO", 20000, "RO Plant"),
	("WIP-WTR-OZ", 18000, "RO Plant"),
	("WIP-BTL-600", 30000, "Line 1 - Small PET"),
	("FG-BOT-600", 28000, "Line 1 - Small PET"),
	("FG-PCK-600-24", 1100, "Line 1 - Small PET"),
]


def run_production(company, posting_date):
	"""Walk the whole BOM tree bottom-up, one work order per level, so the
	demo shows real multi-level costing rather than a single flat build."""
	a = abbr(company)
	fg_wh = f"Finished Goods Store - {a}"
	wip_wh = f"Work In Progress - {a}"
	created = {"work_orders": [], "quality_checks": [], "stock_entries": []}

	for item, qty, line in PRODUCTION_CHAIN:
		if not frappe.db.exists("Item", item):
			continue
		bom = frappe.db.get_value("BOM", {"item": item, "is_active": 1, "is_default": 1}, "name")
		if not bom:
			continue

		target = fg_wh if item.startswith("FG-") else wip_wh
		try:
			wo = _new(
				"Work Order",
				{
					"production_item": item,
					"bom_no": bom,
					"qty": qty,
					"company": company,
					"fg_warehouse": target,
					"wip_warehouse": wip_wh,
					"source_warehouse": f"Raw Material Store - {a}",
					"planned_start_date": posting_date,
					"expected_delivery_date": add_days(posting_date, 1),
					"neoaqua_production_line": line,
					"neoaqua_shift": random.choice(["A", "B"]),
					# skip the WIP transfer so the demo is one clean manufacture
					# entry per level rather than two
					"skip_transfer": 1,
				},
				submit=True,
			)
			created["work_orders"].append(wo.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: work order {item}")
			continue

		batch = frappe.db.get_value("Work Order", wo.name, "neoaqua_batch_no")

		# quality gate before the finished goods can move
		if batch and frappe.get_cached_value("Item", item, "neoaqua_requires_qc"):
			try:
				qc = _new(
					"Water Quality Check",
					{
						"check_type": "Finished Goods",
						"posting_date": posting_date,
						"company": company,
						"work_order": wo.name,
						"item_code": item,
						"batch_no": batch,
						"production_line": line,
						"shift": "A",
						"total_plate_count": random.randint(2, 20),
						"coliform": "Absent",
						"pseudomonas": "Absent",
						"yeast_mould": "Absent",
						"overall_result": "Pass",
						"inspected_by": frappe.db.get_value("Employee", {}, "name"),
					},
					submit=True,
					before_submit=fill_quality_parameters,
				)
				created["quality_checks"].append(qc.name)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: QC for {item}")

		# manufacture
		try:
			from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

			se = make_stock_entry(wo.name, "Manufacture", qty)
			se = frappe.get_doc(se)
			se.posting_date = posting_date
			se.set_posting_time = 1
			se.flags.ignore_permissions = True
			se.flags.ignore_mandatory = True
			se.insert()
			se.submit()
			track(se)
			created["stock_entries"].append(se.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: manufacture {item}")

	return created


# ================================================================== van sales
def run_van_sales(company, posting_date, customers):
	"""Load three vans, check in at each stop, invoice, collect, return and
	settle. This is the path most of the app's controllers sit on."""
	a = abbr(company)
	created = {"trips": [], "invoices": [], "check_ins": [], "day_closes": []}

	sellable = [
		code for code in ("FG-PCK-600-24", "FG-BOT-600", "FG-BOT-330", "FG-BOT-1500")
		if frappe.db.exists("Item", code)
	]
	if not sellable:
		return created

	for van_name, route in (("Van 01", "Riyadh - North Route"),
	                        ("Van 02", "Riyadh - South Route"),
	                        ("Van 03", "Riyadh - East Route")):
		if not frappe.db.exists("Van", van_name):
			continue
		van = frappe.get_doc("Van", van_name)
		if not van.salesman:
			continue

		load = []
		for code in sellable:
			avail = flt(
				frappe.db.get_value(
					"Bin", {"item_code": code, "warehouse": f"Finished Goods Store - {a}"}, "actual_qty"
				)
			)
			if avail <= 0:
				continue
			load.append({"item_code": code, "loaded_qty": min(avail * 0.15, 200)})
		if not load:
			continue

		try:
			trip = _new(
				"Van Trip",
				{
					"trip_date": posting_date,
					"company": company,
					"van": van_name,
					"route": route if frappe.db.exists("Van Route", route) else None,
					"salesman": van.salesman,
					"shift": "Morning",
					"odometer_start": random.randint(40000, 90000),
					"items": load,
					"containers_loaded": 40,
				},
				submit=True,
			)
			created["trips"].append(trip.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: trip for {van_name}")
			continue

		trip_customers = [s.customer for s in trip.stops] or customers[:3]
		invoices, collected = [], 0

		for cust in trip_customers[:4]:
			zone = frappe.db.get_value("Customer", cust, "neoaqua_geofence_zone")
			lat = flt(frappe.db.get_value("Geofence Zone", zone, "center_latitude")) if zone else 24.71
			lng = flt(frappe.db.get_value("Geofence Zone", zone, "center_longitude")) if zone else 46.67

			# a real check-in sits a few metres off the pin
			try:
				ci = _new(
					"Salesman Check In",
					{
						"salesman": van.salesman,
						"checkin_datetime": f"{posting_date} 08:{random.randint(10, 55)}:00",
						"customer": cust,
						"van_trip": trip.name,
						"visit_purpose": "Sale",
						"visit_status": "Successful",
						"latitude": lat + random.uniform(-0.0004, 0.0004),
						"longitude": lng + random.uniform(-0.0004, 0.0004),
						"accuracy_m": random.randint(4, 18),
					},
					submit=True,
				)
				created["check_ins"].append(ci.name)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: check-in {cust}")

			is_cash = frappe.db.get_value("Customer", cust, "customer_group") == "Retail Baqala"
			items = []
			for code in sellable[:3]:
				qty = random.randint(4, 25)
				rate = flt(
					frappe.db.get_value(
						"Item Price",
						{"item_code": code, "price_list": "NeoAqua Retail"},
						"price_list_rate",
					)
				) or 1
				items.append(
					{
						"item_code": code,
						"qty": qty,
						"rate": rate,
						"warehouse": van.warehouse,
						"cost_center": frappe.db.get_value(
							"Cost Center", {"company": company, "cost_center_name": "Distribution"}, "name"
						),
					}
				)

			try:
				si_values = {
					"customer": cust,
					"company": company,
					"posting_date": posting_date,
					"set_posting_time": 1,
					"due_date": add_days(posting_date, 30 if not is_cash else 0),
					"currency": "SAR",
					"conversion_rate": 1,
					"update_stock": 1,
					"neoaqua_van_trip": trip.name,
					"items": items,
					"taxes_and_charges": f"KSA VAT 15% - {a}"
					if frappe.db.exists("Sales Taxes and Charges Template", f"KSA VAT 15% - {a}")
					else None,
				}
				si = frappe.new_doc("Sales Invoice")
				si.update(si_values)
				if si.taxes_and_charges:
					from erpnext.controllers.accounts_controller import get_taxes_and_charges

					for t in get_taxes_and_charges("Sales Taxes and Charges Template", si.taxes_and_charges):
						si.append("taxes", t)
				si.flags.ignore_permissions = True
				si.flags.ignore_mandatory = True
				si.insert()

				if is_cash:
					si.is_pos = 1
					si.append(
						"payments",
						{"mode_of_payment": "Cash", "amount": si.grand_total},
					)
					si.save()
				si.submit()
				track(si)
				invoices.append(si.name)
				created["invoices"].append(si.name)
				if is_cash:
					collected += flt(si.grand_total)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: invoice for {cust}")

		# a credit collection against one of the open invoices
		open_inv = None
		for name in invoices:
			if flt(frappe.db.get_value("Sales Invoice", name, "outstanding_amount")) > 0:
				open_inv = name
				break
		if open_inv:
			try:
				from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

				pe = get_payment_entry("Sales Invoice", open_inv)
				pe.posting_date = posting_date
				pe.mode_of_payment = "Cash"
				pe.reference_no = f"RCPT-{random_string(5).upper()}"
				pe.reference_date = posting_date
				pe.neoaqua_van_trip = trip.name
				pe.flags.ignore_permissions = True
				pe.flags.ignore_mandatory = True
				pe.insert()
				pe.submit()
				track(pe)
				collected += flt(pe.paid_amount)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "NeoAqua demo: collection")

		# container movement for the HOD accounts
		for cust in trip_customers:
			if frappe.db.get_value("Customer", cust, "customer_group") != "Home & Office Delivery":
				continue
			try:
				_new(
					"Container Ledger Entry",
					{
						"posting_date": posting_date,
						"company": company,
						"customer": cust,
						"entry_type": "Issue (Full Out)",
						"item_code": "RM-BTL-PC-189",
						"qty": random.randint(5, 15),
						"van_trip": trip.name,
					},
					submit=True,
				)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "NeoAqua demo: container entry")

		# ---- settle the day
		try:
			trip.reload()
			trip.pull_sold_quantities()
			trip.db_set("odometer_end", flt(trip.odometer_start) + random.randint(60, 180))
			trip.db_set("status", "Returned")

			dc = frappe.new_doc("Salesman Day Close")
			dc.update(
				{
					"posting_date": posting_date,
					"company": company,
					"salesman": van.salesman,
					"van": van_name,
					"van_trip": trip.name,
					"opening_float": 500,
				}
			)
			dc.flags.ignore_permissions = True
			dc.flags.ignore_mandatory = True
			dc.insert()
			dc.fetch_trip_activity()
			dc.reload()

			# return whatever did not sell, plus a little breakage
			for row in dc.stock_items:
				remaining = flt(row.loaded_qty) - flt(row.sold_qty)
				if remaining > 1:
					row.damaged_qty = 1
					row.returned_qty = remaining - 1
				else:
					row.returned_qty = max(remaining, 0)

			for label, amount in (("Fuel", 120), ("Loading Labour", 60)):
				account = frappe.db.get_value(
					"Account",
					{"company": company, "account_name": {"Fuel": "Fuel", "Loading Labour": "Loading and Unloading Labour"}[label], "is_group": 0},
					"name",
				)
				if account:
					dc.append("expenses", {"expense_type": label, "expense_account": account, "amount": amount})

			dc.save()
			dc.reload()
			# a small, believable shortage on one van
			dc.declared_cash = flt(dc.expected_cash) - (12 if van_name == "Van 02" else 0)
			if van_name == "Van 02":
				dc.variance_reason = "Short change given at Baqala Al Salam, acknowledged by salesman."
				dc.variance_treatment = "Recover from Salesman"
			dc.deposit_mode = "Cash to Cashier"
			dc.deposit_amount = flt(dc.declared_cash)
			dc.deposit_reference = f"DEP-{random_string(5).upper()}"
			dc.save()
			dc.submit()
			track(dc)
			created["day_closes"].append(dc.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"NeoAqua demo: day close for {van_name}")

	return created


# ================================================================== guards
def _require_plant(company):
	"""Demo data needs the item master and BOM tree to exist first.

	The message has to be actionable from wherever the caller is standing -
	pointing a browser user at a bench command is not help.
	"""
	from neoaqua.setup import orchestrator

	state = orchestrator.status(company)
	if state.get("complete"):
		return

	missing = [c for c in state["checks"] if not c["ok"]]
	rows = "".join(
		f"<tr><td>{frappe.utils.escape_html(c['check'])}</td>"
		f"<td style='text-align:right'>{c['actual']} / {c['expected']}</td></tr>"
		for c in missing[:10]
	)
	frappe.throw(
		_("The plant is not set up yet, so there is nothing for the demo to trade with.")
		+ "<br><br>"
		+ _("Use <b>Run Plant Setup</b> on this page, then generate the demo data.")
		+ "<br><br><table class='table table-bordered' style='font-size:12px'>"
		+ f"<thead><tr><th>{_('Missing')}</th><th style='text-align:right'>{_('Have / Need')}</th></tr></thead>"
		+ f"<tbody>{rows}</tbody></table>",
		title=_("Plant Setup Required"),
	)


# ================================================================== entry
@frappe.whitelist()
def generate(company=None, demo_days=7, include_procurement=1,
             include_production=1, include_van_sales=1):
	company = company or frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw(_("Select a Company first."))
	_require_plant(company)

	demo_days = int(demo_days or 7)
	start = add_days(nowdate(), -demo_days)
	run_id = start_run()
	log = {"run_id": run_id, "company": company}

	log["suppliers"] = create_suppliers(company)
	log["customers"] = create_customers(company)
	log["salesmen"] = create_salesmen(company, log["customers"])

	opening = create_opening_stock(company, start)
	log["opening_stock"] = opening.name if opening else None

	if int(include_procurement or 0):
		log["procurement"] = run_procurement(company, add_days(start, 1), log["suppliers"])
	if int(include_production or 0):
		log["production"] = run_production(company, add_days(start, 3))
	if int(include_van_sales or 0):
		log["van_sales"] = run_van_sales(company, add_days(start, 5), log["customers"])

	count = frappe.db.count("NeoAqua Demo Record", {"run_id": run_id})

	tool = frappe.get_single("NeoAqua Demo Tool")
	tool.company = company
	tool.last_run_id = run_id
	tool.last_run_on = frappe.utils.now_datetime()
	tool.records_created = count
	tool.run_log = json.dumps(log, indent=2, default=str)
	tool.flags.ignore_permissions = True
	tool.save()

	frappe.db.commit()
	return {"run_id": run_id, "documents": count, "log": log}
