frappe.query_reports["Batch QC Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "check_type", label: __("Check Type"), fieldtype: "Select",
		  options: ["", "Source Water", "Post-RO", "Post-Ozonation", "In-Process (Filler)", "Finished Goods", "Retention Sample"] },
		{ fieldname: "overall_result", label: __("Result"), fieldtype: "Select",
		  options: ["", "Pass", "Fail", "Conditional Release"] },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "batch_no", label: __("Batch"), fieldtype: "Link", options: "Batch" },
	],
};
