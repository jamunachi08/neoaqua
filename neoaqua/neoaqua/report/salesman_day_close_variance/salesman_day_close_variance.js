frappe.query_reports["Salesman Day Close Variance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "salesman", label: __("Salesman"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "van", label: __("Van"), fieldtype: "Link", options: "Van" },
		{ fieldname: "only_variance", label: __("Only Rows with Variance"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "cash_variance" && data && data.cash_variance) {
			const c = data.cash_variance < 0 ? "red" : "blue";
			value = `<span style="color:${c};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
