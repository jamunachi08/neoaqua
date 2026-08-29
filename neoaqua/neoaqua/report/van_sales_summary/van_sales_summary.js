frappe.query_reports["Van Sales Summary"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "van", label: __("Van"), fieldtype: "Link", options: "Van" },
		{ fieldname: "salesman", label: __("Salesman"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "route", label: __("Route"), fieldtype: "Link", options: "Van Route" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "sell_through" && data) {
			const c = data.sell_through < 60 ? "red" : data.sell_through < 80 ? "orange" : "green";
			value = `<span style="color:var(--text-on-${c},${c})">${value}</span>`;
		}
		return value;
	},
};
