frappe.query_reports["Production Yield and Scrap"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "production_line", label: __("Production Line"), fieldtype: "Select",
		  options: ["", "Line 1 - Small PET", "Line 2 - Large PET", "Line 3 - 5 Gallon", "RO Plant"] },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
	],
};
