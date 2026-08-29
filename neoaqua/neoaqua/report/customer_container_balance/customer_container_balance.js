frappe.query_reports["Customer Container Balance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "as_on_date", label: __("As On"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "only_exposure", label: __("Only Uncovered Exposure"), fieldtype: "Check" },
	],
};
