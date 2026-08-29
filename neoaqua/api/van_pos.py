# Copyright (c) 2026, Neotec Integrated Solutions
"""Van POS endpoints for the salesman's handheld.

The day, as it actually runs:

    load the van  ->  drive the area  ->  at each customer, decide the quantity
    at the door and drop it  ->  invoice on the spot  ->  print  ->  take money
    for this delivery, for earlier ones, for both, or for none

Two kinds of stop, and they are not the same transaction:

  * VAN SALE - the ordinary case. Nobody ordered anything in advance. The
    salesman and the customer agree quantities at the door, stock moves off the
    van, and the invoice is created and printed there and then.

  * ORDER DELIVERY - the customer phoned the office. A Sales Order already
    exists, so the salesman is delivering against it, not selling. The invoice
    is made FROM the order, which keeps the order's agreed prices and closes it
    properly instead of leaving it open forever.

Collection is deliberately decoupled from both. Money taken at the door may
settle today's invoice, older ones, part of either, or nothing at all - so the
collection endpoint takes an amount and an optional allocation, and defaults to
oldest-first when the salesman does not specify.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, nowdate

from neoaqua.van_sales import geofence


# ---------------------------------------------------------------- identity
def _me():
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	salesman = frappe.db.get_value("Sales Person", {"employee": employee}, "name") if employee else None
	if not salesman:
		frappe.throw(_("This user is not linked to a Sales Person."), frappe.PermissionError)
	return salesman


def _open_trip(salesman=None):
	salesman = salesman or _me()
	trip = frappe.db.get_value(
		"Van Trip",
		{"salesman": salesman, "docstatus": 1, "status": ["in", ["Loaded", "In Progress"]]},
		["name", "van", "van_warehouse", "company", "route", "trip_date"],
		as_dict=True,
	)
	if not trip:
		frappe.throw(_("No open van trip. Load the van first."))
	return trip


def _parse(value, default=None):
	if value in (None, ""):
		return default
	if isinstance(value, str):
		return json.loads(value)
	return value


# ---------------------------------------------------------------- day plan
@frappe.whitelist()
def route_plan():
	"""Everything the handheld needs to render the day.

	Each stop is typed, so the app can show "deliver order SO-0042" rather than
	an empty sell screen for a customer who already ordered."""
	trip = _open_trip()
	stops = []

	planned = frappe.get_all(
		"Van Trip Stop",
		filters={"parent": trip.name},
		fields=["customer", "customer_name", "sequence", "status", "stop_type", "sales_order"],
		order_by="sequence asc",
	)

	pending_orders = _pending_orders_map(trip)

	for s in planned:
		orders = pending_orders.pop(s.customer, [])
		stops.append(
			{
				"customer": s.customer,
				"customer_name": s.customer_name,
				"sequence": s.sequence,
				"status": s.status,
				"stop_type": s.stop_type or ("Order Delivery" if orders else "Van Sale"),
				"pending_orders": orders,
				"outstanding": _outstanding_total(s.customer),
			}
		)

	# a customer who ordered but is not on the route still has to be visited
	for customer, orders in pending_orders.items():
		stops.append(
			{
				"customer": customer,
				"customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
				"sequence": 999,
				"status": "Pending",
				"stop_type": "Order Delivery",
				"pending_orders": orders,
				"outstanding": _outstanding_total(customer),
				"off_route": True,
			}
		)

	return {
		"trip": trip.name,
		"van": trip.van,
		"date": str(trip.trip_date),
		"stops": stops,
		"van_stock": van_stock(),
	}


def _pending_orders_map(trip):
	"""Open Sales Orders for this trip's route, grouped by customer."""
	customers = []
	if trip.route:
		customers = frappe.get_all("Van Route Stop", filters={"parent": trip.route}, pluck="customer")
	filters = {
		"docstatus": 1,
		"status": ["not in", ["Closed", "Completed", "Cancelled"]],
		"company": trip.company,
	}
	if customers:
		filters["customer"] = ["in", customers]

	out = {}
	for so in frappe.get_all(
		"Sales Order",
		filters=filters,
		fields=["name", "customer", "transaction_date", "grand_total", "per_delivered", "delivery_date"],
		order_by="transaction_date asc",
		limit=200,
	):
		if flt(so.per_delivered) >= 100:
			continue
		out.setdefault(so.customer, []).append(
			{
				"sales_order": so.name,
				"date": str(so.transaction_date),
				"amount": flt(so.grand_total),
				"delivered_pct": flt(so.per_delivered),
			}
		)
	return out


@frappe.whitelist()
def van_stock():
	trip = _open_trip()
	rows = frappe.db.sql(
		"""select b.item_code, i.item_name, i.stock_uom, b.actual_qty
		   from `tabBin` b join `tabItem` i on i.name = b.item_code
		   where b.warehouse = %s and b.actual_qty > 0
		   order by i.item_name""",
		trip.van_warehouse,
		as_dict=True,
	)
	price_list = frappe.db.get_value("POS Profile", {"warehouse": trip.van_warehouse}, "selling_price_list")
	for r in rows:
		r["rate"] = flt(
			frappe.db.get_value(
				"Item Price",
				{"item_code": r.item_code, "price_list": price_list or "NeoAqua Retail"},
				"price_list_rate",
			)
		)
	return rows


# ---------------------------------------------------------------- van sale
@frappe.whitelist()
def van_sale(customer, items, paid_amount=0, mode_of_payment="Cash",
             latitude=None, longitude=None, containers_out=0, empties_in=0,
             remarks=None):
	"""The ordinary stop: quantities agreed at the door, stock off the van,
	invoice raised and printed on the spot.

	`items` is [{"item_code": "FG-PCK-600-24", "qty": 5, "rate": 21.0}, ...].
	`rate` is optional - the van's price list applies when it is omitted.
	Partial payment is normal, so `paid_amount` may be less than the total and
	the balance simply stays outstanding.
	"""
	trip = _open_trip()
	items = _parse(items, [])
	if not items:
		frappe.throw(_("Add at least one line before invoicing."))

	_check_in_if_needed(trip, customer, latitude, longitude, "Sale")

	si = frappe.new_doc("Sales Invoice")
	si.update(
		{
			"customer": customer,
			"company": trip.company,
			"posting_date": nowdate(),
			"set_posting_time": 1,
			"update_stock": 1,
			"neoaqua_van_trip": trip.name,
			"neoaqua_sale_type": "Van Sale",
			"neoaqua_containers_out": containers_out,
			"neoaqua_empties_collected": empties_in,
			"neoaqua_latitude": latitude,
			"neoaqua_longitude": longitude,
			"remarks": remarks,
		}
	)
	for row in items:
		si.append(
			"items",
			{
				"item_code": row["item_code"],
				"qty": flt(row["qty"]),
				"rate": flt(row.get("rate")) or None,
				"warehouse": trip.van_warehouse,
			},
		)

	_apply_tax_template(si)
	si.flags.ignore_permissions = True
	si.insert()

	if flt(paid_amount) > 0:
		si.is_pos = 1
		si.append("payments", {"mode_of_payment": mode_of_payment, "amount": flt(paid_amount)})
		si.save()

	si.submit()
	_mark_stop(trip.name, customer, si.name, flt(si.grand_total), flt(paid_amount))

	return receipt(si.name)


# ---------------------------------------------------------------- delivery
@frappe.whitelist()
def deliver_order(sales_order, items=None, paid_amount=0, mode_of_payment="Cash",
                  latitude=None, longitude=None, remarks=None):
	"""The customer ordered through the office. Invoice FROM the order so the
	agreed prices carry over and the order closes instead of hanging open.

	`items` optionally overrides the delivered quantity per line, because what
	leaves the van is not always what was ordered - short delivery is normal
	and the order should reflect it.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	trip = _open_trip()
	so = frappe.get_doc("Sales Order", sales_order)
	if so.docstatus != 1:
		frappe.throw(_("Sales Order {0} is not submitted.").format(sales_order))

	_check_in_if_needed(trip, so.customer, latitude, longitude, "Delivery")

	si = make_sales_invoice(sales_order)
	si.update(
		{
			"posting_date": nowdate(),
			"set_posting_time": 1,
			"update_stock": 1,
			"neoaqua_van_trip": trip.name,
			"neoaqua_sale_type": "Order Delivery",
			"neoaqua_latitude": latitude,
			"neoaqua_longitude": longitude,
			"remarks": remarks,
		}
	)

	# An override adjusts ONLY the lines it names. Lines the handheld does not
	# mention keep the ordered quantity - the alternative, treating silence as
	# zero, means a client that sends just the one changed line silently drops
	# the rest of the delivery. To remove a line, send it explicitly with
	# qty 0.
	overrides = {r["item_code"]: flt(r["qty"]) for r in (_parse(items, []) or [])}
	keep = []
	for row in si.items:
		row.warehouse = trip.van_warehouse
		if overrides:
			row.qty = overrides.get(row.item_code, row.qty)
		if flt(row.qty) > 0:
			keep.append(row)
	if overrides:
		si.items = keep
		for i, row in enumerate(si.items, start=1):
			row.idx = i
	if not si.items:
		frappe.throw(_("Nothing left to deliver on this order."))

	si.flags.ignore_permissions = True
	si.insert()

	if flt(paid_amount) > 0:
		si.is_pos = 1
		si.append("payments", {"mode_of_payment": mode_of_payment, "amount": flt(paid_amount)})
		si.save()

	si.submit()
	_mark_stop(trip.name, so.customer, si.name, flt(si.grand_total), flt(paid_amount))

	return receipt(si.name)


# ---------------------------------------------------------------- collection
@frappe.whitelist()
def customer_outstanding(customer):
	"""Aged list for the collection screen - what this customer owes, oldest
	first, which is the order money is normally applied in."""
	rows = frappe.db.sql(
		"""select name, posting_date, due_date, grand_total, outstanding_amount
		   from `tabSales Invoice`
		   where customer = %s and docstatus = 1 and outstanding_amount > 0.005
		   order by posting_date asc, name asc""",
		customer,
		as_dict=True,
	)
	today = getdate(nowdate())
	for r in rows:
		r["age_days"] = (today - getdate(r.posting_date)).days
		r["overdue"] = bool(r.due_date and getdate(r.due_date) < today)
		r["posting_date"] = str(r.posting_date)
		r["due_date"] = str(r.due_date) if r.due_date else None
	return {
		"customer": customer,
		"customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
		"total_outstanding": sum(flt(r.outstanding_amount) for r in rows),
		"invoices": rows,
	}


def _outstanding_total(customer):
	return flt(
		frappe.db.sql(
			"""select sum(outstanding_amount) from `tabSales Invoice`
			   where customer = %s and docstatus = 1""",
			customer,
		)[0][0]
	)


@frappe.whitelist()
def collect(customer, amount, mode_of_payment="Cash", allocations=None,
            reference_no=None, latitude=None, longitude=None):
	"""Take money at the door.

	It may settle today's invoice, earlier ones, part of either, or sit on
	account as an advance. Pass `allocations` as
	[{"sales_invoice": "SINV-0001", "amount": 50}] to direct it; leave it out
	and the payment is applied oldest invoice first, which is what a salesman
	means by "he paid me two hundred".
	"""
	trip = _open_trip()
	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Enter an amount greater than zero."))

	allocations = _parse(allocations, None)
	if not allocations:
		allocations = _allocate_oldest_first(customer, amount)

	company = trip.company
	settings = frappe.get_cached_doc("NeoAqua Settings")
	paid_to = settings.cash_account or frappe.db.get_value(
		"Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name"
	)
	receivable = frappe.db.get_value("Company", company, "default_receivable_account")

	pe = frappe.new_doc("Payment Entry")
	pe.update(
		{
			"payment_type": "Receive",
			"company": company,
			"posting_date": nowdate(),
			"mode_of_payment": mode_of_payment,
			"party_type": "Customer",
			"party": customer,
			"paid_amount": amount,
			"received_amount": amount,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"paid_to": paid_to,
			"paid_from": receivable,
			"reference_no": reference_no or f"VAN-{trip.van}",
			"reference_date": nowdate(),
			"neoaqua_van_trip": trip.name,
		}
	)
	for a in allocations:
		pe.append(
			"references",
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": a["sales_invoice"],
				"allocated_amount": flt(a["amount"]),
			},
		)

	pe.flags.ignore_permissions = True
	pe.flags.ignore_mandatory = True
	pe.insert()
	pe.submit()

	unallocated = amount - sum(flt(a["amount"]) for a in allocations)
	return {
		"payment_entry": pe.name,
		"amount": amount,
		"allocated": amount - unallocated,
		"on_account": unallocated,
		"remaining_outstanding": _outstanding_total(customer),
	}


def _allocate_oldest_first(customer, amount):
	remaining = flt(amount)
	out = []
	for inv in customer_outstanding(customer)["invoices"]:
		if remaining <= 0.005:
			break
		take = min(remaining, flt(inv["outstanding_amount"]))
		out.append({"sales_invoice": inv["name"], "amount": take})
		remaining -= take
	return out


# ---------------------------------------------------------------- receipt
@frappe.whitelist()
def receipt(sales_invoice):
	"""Payload for the handheld's thermal printer."""
	si = frappe.get_doc("Sales Invoice", sales_invoice)
	company = frappe.get_cached_doc("Company", si.company)
	settings = frappe.get_cached_doc("NeoAqua Settings")

	return {
		"invoice": si.name,
		"sale_type": si.get("neoaqua_sale_type"),
		"posting_date": str(si.posting_date),
		"posting_time": str(si.posting_time),
		"company": si.company,
		"vat_number": company.get("tax_id"),
		"cr_number": company.get("registration_details"),
		"sfda_licence": settings.get("sfda_licence_no"),
		"customer": si.customer,
		"customer_name": si.customer_name,
		"salesman": si.get("neoaqua_salesman"),
		"van": si.get("neoaqua_van"),
		"items": [
			{
				"item_code": r.item_code,
				"item_name": r.item_name,
				"qty": flt(r.qty),
				"uom": r.uom,
				"rate": flt(r.rate),
				"amount": flt(r.amount),
			}
			for r in si.items
		],
		"net_total": flt(si.net_total),
		"total_taxes": flt(si.total_taxes_and_charges),
		"grand_total": flt(si.grand_total),
		"rounded_total": flt(si.rounded_total or si.grand_total),
		"paid_amount": flt(si.paid_amount),
		"outstanding": flt(si.outstanding_amount),
		"qr_code": si.get("ksa_einv_qr"),
		"print_format": "NeoAqua Van Receipt 80mm",
	}


# ---------------------------------------------------------------- helpers
def _apply_tax_template(si):
	abbr = frappe.get_cached_value("Company", si.company, "abbr")
	template = f"KSA VAT 15% - {abbr}"
	if not frappe.db.exists("Sales Taxes and Charges Template", template):
		return
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	si.taxes_and_charges = template
	for t in get_taxes_and_charges("Sales Taxes and Charges Template", template):
		si.append("taxes", t)


def _check_in_if_needed(trip, customer, latitude, longitude, purpose):
	"""Log the visit automatically when the handheld sends coordinates, so the
	salesman is not asked to check in as a separate step."""
	if latitude in (None, "") or longitude in (None, ""):
		return None
	if geofence.has_valid_checkin(customer, frappe.db.get_value("Van Trip", trip.name, "salesman")):
		return None

	doc = frappe.new_doc("Salesman Check In")
	doc.update(
		{
			"salesman": frappe.db.get_value("Van Trip", trip.name, "salesman"),
			"customer": customer,
			"van_trip": trip.name,
			"checkin_datetime": now_datetime(),
			"visit_purpose": purpose,
			"visit_status": "Successful",
			"latitude": flt(latitude),
			"longitude": flt(longitude),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


def _mark_stop(trip, customer, invoice, amount, collected):
	doc = frappe.get_doc("Van Trip", trip)
	touched = False
	for stop in doc.stops:
		if stop.customer == customer and stop.status == "Pending":
			stop.status = "Visited"
			stop.sales_invoice = invoice
			stop.invoice_amount = amount
			stop.collected_amount = collected
			touched = True
			break
	if not touched:
		doc.append(
			"stops",
			{
				"customer": customer,
				"sequence": len(doc.stops) + 1,
				"status": "Visited",
				"sales_invoice": invoice,
				"invoice_amount": amount,
				"collected_amount": collected,
			},
		)
	if doc.status == "Loaded":
		doc.db_set("status", "In Progress")
	doc.calculate_coverage()
	doc.flags.ignore_permissions = True
	doc.save()
