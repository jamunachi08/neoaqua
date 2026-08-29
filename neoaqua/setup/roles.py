# Copyright (c) 2026, Neotec Integrated Solutions
"""Role and role-profile creation."""

import frappe

ROLES = [
	("NeoAqua Manager", 0),
	("Van Salesman", 0),
	("Van Supervisor", 0),
	("Plant Operator", 0),
	("QC Inspector", 0),
	("Cashier - Water", 0),
]

ROLE_PROFILES = {
	"Van Salesman": ["Van Salesman", "Sales User", "Accounts User", "Stock User"],
	"Van Supervisor": ["Van Supervisor", "Sales Manager", "Accounts User", "Stock Manager"],
	"Plant Supervisor": ["Plant Operator", "Manufacturing User", "Stock User", "Item Manager"],
	"Water QC": ["QC Inspector", "Quality Manager", "Stock User"],
}


def install():
	for role, desk in ROLES:
		if frappe.db.exists("Role", role):
			continue
		doc = frappe.new_doc("Role")
		doc.role_name = role
		doc.desk_access = 1
		doc.two_factor_auth = 0
		doc.flags.ignore_permissions = True
		doc.insert()

	for profile, roles in ROLE_PROFILES.items():
		if frappe.db.exists("Role Profile", profile):
			continue
		doc = frappe.new_doc("Role Profile")
		doc.role_profile = profile
		for r in roles:
			if frappe.db.exists("Role", r):
				doc.append("roles", {"role": r})
		doc.flags.ignore_permissions = True
		doc.insert()
	frappe.db.commit()
