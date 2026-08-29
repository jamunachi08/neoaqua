# Copyright (c) 2026, Neotec Integrated Solutions
"""Custom fields injected into standard ERPNext doctypes.

All fields are prefixed `neoaqua_` and tagged with module "NeoAqua" so the
fixtures export in hooks.py picks them up cleanly and an uninstall can remove
them without touching anyone else's customisations.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_custom_fields():
	van_trip_fields = [
		{
			"fieldname": "neoaqua_van_sales_sb",
			"label": "Van Sales",
			"fieldtype": "Section Break",
			"insert_after": "company",
			"collapsible": 1,
		},
		{
			"fieldname": "neoaqua_van_trip",
			"label": "Van Trip",
			"fieldtype": "Link",
			"options": "Van Trip",
			"insert_after": "neoaqua_van_sales_sb",
			"search_index": 1,
		},
		{
			"fieldname": "neoaqua_van",
			"label": "Van",
			"fieldtype": "Link",
			"options": "Van",
			"insert_after": "neoaqua_van_trip",
			"read_only": 1,
		},
		{"fieldname": "neoaqua_cb_van", "fieldtype": "Column Break", "insert_after": "neoaqua_van"},
		{
			"fieldname": "neoaqua_salesman",
			"label": "Salesman",
			"fieldtype": "Link",
			"options": "Sales Person",
			"insert_after": "neoaqua_cb_van",
			"read_only": 1,
		},
	]

	return {
		"Sales Invoice": van_trip_fields
		+ [
			{
				"fieldname": "neoaqua_sale_type",
				"label": "Sale Type",
				"fieldtype": "Select",
				"options": "\nVan Sale\nOrder Delivery\nCounter Sale",
				"insert_after": "neoaqua_salesman",
				"in_standard_filter": 1,
				"description": "Van Sale is agreed at the door; Order Delivery fulfils an order taken at the office.",
			},
			{
				"fieldname": "neoaqua_containers_out",
				"label": "Full Containers Issued",
				"fieldtype": "Int",
				"insert_after": "neoaqua_sale_type",
				"depends_on": "eval:frappe.boot.neoaqua_track_containers",
			},
			{
				"fieldname": "neoaqua_empties_collected",
				"label": "Empty Containers Collected",
				"fieldtype": "Int",
				"insert_after": "neoaqua_containers_out",
			},
			{
				"fieldname": "neoaqua_latitude",
				"label": "Invoice Latitude",
				"fieldtype": "Float",
				"insert_after": "neoaqua_empties_collected",
				"precision": "6",
				"read_only": 1,
				"print_hide": 1,
			},
			{
				"fieldname": "neoaqua_longitude",
				"label": "Invoice Longitude",
				"fieldtype": "Float",
				"insert_after": "neoaqua_latitude",
				"precision": "6",
				"read_only": 1,
				"print_hide": 1,
			},
		],
		"POS Invoice": van_trip_fields,
		"Payment Entry": [
			{
				"fieldname": "neoaqua_van_trip",
				"label": "Van Trip",
				"fieldtype": "Link",
				"options": "Van Trip",
				"insert_after": "company",
				"search_index": 1,
			}
		],
		"Stock Entry": [
			{
				"fieldname": "neoaqua_van_trip",
				"label": "Van Trip",
				"fieldtype": "Link",
				"options": "Van Trip",
				"insert_after": "company",
				"search_index": 1,
			}
		],
		"Delivery Note": van_trip_fields,
		"Work Order": [
			{
				"fieldname": "neoaqua_production_line",
				"label": "Production Line",
				"fieldtype": "Select",
				"options": "\nLine 1 - Small PET\nLine 2 - Large PET\nLine 3 - 5 Gallon\nRO Plant",
				"insert_after": "company",
				"in_standard_filter": 1,
			},
			{
				"fieldname": "neoaqua_shift",
				"label": "Shift",
				"fieldtype": "Select",
				"options": "\nA\nB\nC",
				"insert_after": "neoaqua_production_line",
			},
			{
				"fieldname": "neoaqua_batch_no",
				"label": "Reserved Batch",
				"fieldtype": "Link",
				"options": "Batch",
				"insert_after": "neoaqua_shift",
				"read_only": 1,
				"allow_on_submit": 1,
				"no_copy": 1,
			},
		],
		"Item": [
			{
				"fieldname": "neoaqua_sb",
				"label": "NeoAqua",
				"fieldtype": "Section Break",
				"insert_after": "shelf_life_in_days",
				"collapsible": 1,
			},
			{
				"fieldname": "neoaqua_requires_qc",
				"label": "Requires Water Quality Check",
				"fieldtype": "Check",
				"insert_after": "neoaqua_sb",
			},
			{
				"fieldname": "neoaqua_food_contact",
				"label": "Food-Contact Material",
				"fieldtype": "Check",
				"insert_after": "neoaqua_requires_qc",
				"description": "Supplier must hold a valid SFDA registration",
			},
			{
				"fieldname": "neoaqua_is_returnable",
				"label": "Returnable Container",
				"fieldtype": "Check",
				"insert_after": "neoaqua_food_contact",
			},
			{"fieldname": "neoaqua_cb", "fieldtype": "Column Break", "insert_after": "neoaqua_is_returnable"},
			{
				"fieldname": "neoaqua_fill_volume_ml",
				"label": "Fill Volume (ml)",
				"fieldtype": "Float",
				"insert_after": "neoaqua_cb",
			},
			{
				"fieldname": "neoaqua_bottles_per_pack",
				"label": "Bottles per Pack",
				"fieldtype": "Int",
				"insert_after": "neoaqua_fill_volume_ml",
			},
			{
				"fieldname": "neoaqua_batch_code",
				"label": "Batch Short Code",
				"fieldtype": "Data",
				"insert_after": "neoaqua_bottles_per_pack",
				"length": 8,
				"description": "Short code used by the Item Batch Code segment, e.g. B600",
			},
			{
				"fieldname": "neoaqua_sfda_product_code",
				"label": "SFDA Product Code",
				"fieldtype": "Data",
				"insert_after": "neoaqua_bottles_per_pack",
			},
		],
		"Supplier": [
			{
				"fieldname": "neoaqua_compliance_sb",
				"label": "KSA Compliance",
				"fieldtype": "Section Break",
				"insert_after": "tax_category",
				"collapsible": 1,
			},
			{
				"fieldname": "neoaqua_sfda_registration",
				"label": "SFDA Registration No",
				"fieldtype": "Data",
				"insert_after": "neoaqua_compliance_sb",
			},
			{
				"fieldname": "neoaqua_cr_number",
				"label": "Commercial Registration No",
				"fieldtype": "Data",
				"insert_after": "neoaqua_sfda_registration",
			},
			{"fieldname": "neoaqua_cb_sup", "fieldtype": "Column Break", "insert_after": "neoaqua_cr_number"},
			{
				"fieldname": "neoaqua_cr_expiry",
				"label": "CR Expiry Date",
				"fieldtype": "Date",
				"insert_after": "neoaqua_cb_sup",
			},
			{
				"fieldname": "neoaqua_supplier_rating",
				"label": "Quality Rating",
				"fieldtype": "Select",
				"options": "\nA - Approved\nB - Conditional\nC - Probation\nD - Blacklisted",
				"insert_after": "neoaqua_cr_expiry",
			},
		],
		"Customer": [
			{
				"fieldname": "neoaqua_sb_cust",
				"label": "NeoAqua Distribution",
				"fieldtype": "Section Break",
				"insert_after": "territory",
				"collapsible": 1,
			},
			{
				"fieldname": "neoaqua_route",
				"label": "Van Route",
				"fieldtype": "Link",
				"options": "Van Route",
				"insert_after": "neoaqua_sb_cust",
			},
			{
				"fieldname": "neoaqua_geofence_zone",
				"label": "Geofence Zone",
				"fieldtype": "Link",
				"options": "Geofence Zone",
				"insert_after": "neoaqua_route",
			},
			{"fieldname": "neoaqua_cb_cust", "fieldtype": "Column Break", "insert_after": "neoaqua_geofence_zone"},
			{
				"fieldname": "neoaqua_container_balance",
				"label": "Containers Held",
				"fieldtype": "Int",
				"insert_after": "neoaqua_cb_cust",
				"read_only": 1,
			},
			{
				"fieldname": "neoaqua_visit_frequency",
				"label": "Visit Frequency",
				"fieldtype": "Select",
				"options": "\nDaily\nAlternate Day\nTwice Weekly\nWeekly\nFortnightly\nOn Call",
				"insert_after": "neoaqua_container_balance",
			},
		],
		"Purchase Receipt": [
			{
				"fieldname": "neoaqua_coa_reference",
				"label": "Certificate of Analysis Ref",
				"fieldtype": "Data",
				"insert_after": "supplier_delivery_note",
			},
			{
				"fieldname": "neoaqua_coa_attachment",
				"label": "Certificate of Analysis",
				"fieldtype": "Attach",
				"insert_after": "neoaqua_coa_reference",
			},
		],
		"Batch": [
			{
				"fieldname": "neoaqua_qc_status",
				"label": "QC Status",
				"fieldtype": "Select",
				"options": "\nPending\nPass\nFail\nConditional Release",
				"insert_after": "batch_qty",
				"read_only": 1,
			},
			{
				"fieldname": "neoaqua_production_line",
				"label": "Production Line",
				"fieldtype": "Data",
				"insert_after": "neoaqua_qc_status",
				"read_only": 1,
			},
			{
				"fieldname": "neoaqua_shift",
				"label": "Shift",
				"fieldtype": "Data",
				"insert_after": "neoaqua_production_line",
				"read_only": 1,
			},
			{
				"fieldname": "neoaqua_work_order",
				"label": "Work Order",
				"fieldtype": "Link",
				"options": "Work Order",
				"insert_after": "neoaqua_shift",
				"read_only": 1,
			},
			{
				"fieldname": "neoaqua_naming_rule",
				"label": "Batch Naming Rule",
				"fieldtype": "Link",
				"options": "Batch Naming Rule",
				"insert_after": "neoaqua_work_order",
				"read_only": 1,
				"description": "The rule that composed this code. Required for decoding.",
			},
		],
		"Sales Person": [
			{
				"fieldname": "neoaqua_default_van",
				"label": "Default Van",
				"fieldtype": "Link",
				"options": "Van",
				"insert_after": "employee",
			}
		],
	}


def install():
	fields = get_custom_fields()
	create_custom_fields(fields, ignore_validate=True)
	# tag them so the fixtures export and the uninstaller can find them
	for doctype, rows in fields.items():
		for row in rows:
			name = f"{doctype}-{row['fieldname']}"
			if frappe.db.exists("Custom Field", name):
				frappe.db.set_value("Custom Field", name, "module", "NeoAqua", update_modified=False)
	frappe.db.commit()


def uninstall():
	for doctype, rows in get_custom_fields().items():
		for row in rows:
			name = f"{doctype}-{row['fieldname']}"
			if frappe.db.exists("Custom Field", name):
				frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	frappe.db.commit()
