frappe.query_reports["Sales Register Van and Channel"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "van", label: __("Van"), fieldtype: "Link", options: "Van" },
		{ fieldname: "salesman", label: __("Salesman"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "customer_group", label: __("Channel"), fieldtype: "Link", options: "Customer Group" },
		{ fieldname: "sale_type", label: __("Sale Type"), fieldtype: "Select",
		  options: ["", "Van Sale", "Order Delivery", "Counter Sale"] },
	],
};
