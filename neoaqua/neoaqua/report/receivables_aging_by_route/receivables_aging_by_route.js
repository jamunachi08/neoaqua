frappe.query_reports["Receivables Aging by Route"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "as_on_date", label: __("As On"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "route", label: __("Route"), fieldtype: "Link", options: "Van Route" },
		{ fieldname: "salesman", label: __("Salesman"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "only_overdue", label: __("Only Overdue"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "b_90_plus" && data && data.b_90_plus > 0) {
			value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
