frappe.query_reports["Customer Sales Trend"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "customer_group", label: __("Channel"), fieldtype: "Link", options: "Customer Group" },
		{ fieldname: "only_declining", label: __("Only Declining and Lost"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "trend" && data) {
			const c = { Lost: "red", Declining: "orange", Growing: "green", New: "blue" }[data.trend];
			if (c) value = `<span class="indicator-pill ${c}">${value}</span>`;
		}
		return value;
	},
};
