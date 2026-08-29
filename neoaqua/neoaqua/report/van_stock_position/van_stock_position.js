frappe.query_reports["Van Stock Position"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "van", label: __("Van"), fieldtype: "Link", options: "Van" },
	],
};
