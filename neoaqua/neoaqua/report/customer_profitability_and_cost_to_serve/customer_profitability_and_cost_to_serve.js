frappe.query_reports["Customer Profitability and Cost to Serve"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "cost_per_visit", label: __("Cost per Visit (SAR)"), fieldtype: "Currency",
		  default: 18, description: __("Fuel, labour and vehicle cost of one drop") },
		{ fieldname: "only_unprofitable", label: __("Only Loss Making"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "verdict" && data) {
			const c = { "Loss making": "red", Marginal: "orange", Star: "green", Healthy: "blue" }[data.verdict];
			if (c) value = `<span class="indicator-pill ${c}">${value}</span>`;
		}
		return value;
	},
};
