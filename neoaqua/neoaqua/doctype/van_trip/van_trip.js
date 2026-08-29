// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Van Trip", {
	refresh(frm) {
		frm.trigger("set_indicators");
		if (frm.doc.docstatus !== 1) return;

		if (["Loaded", "In Progress"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Pull Sold Quantities"), () => {
				frm.call("pull_sold_quantities").then(() => frm.reload_doc());
			}, __("Actions"));

			frm.add_custom_button(__("Return Stock to Plant"), () => {
				frappe.confirm(__("Transfer all returned quantities back to the plant?"), () => {
					frm.call("create_return_stock_entry").then((r) => {
						if (r.message) frappe.set_route("Form", "Stock Entry", r.message);
					});
				});
			}, __("Actions"));

			frm.add_custom_button(__("Pull Pending Orders"), () => {
				frm.call("pull_pending_orders").then((r) => {
					const m = r.message || {};
					frappe.show_alert({
						message: __("{0} order deliveries added", [m.added || 0]),
						indicator: m.added ? "green" : "blue",
					});
					frm.reload_doc();
				});
			}, __("Actions"));

			frm.add_custom_button(__("New Sales Invoice"), () => {
				frappe.new_doc("Sales Invoice", { neoaqua_van_trip: frm.doc.name, is_pos: 1 });
			}, __("Create"));
		}

		if (frm.doc.status === "Returned" && !frm.doc.day_close) {
			frm.add_custom_button(__("Day Close"), () => {
				frappe.new_doc("Salesman Day Close", {
					van_trip: frm.doc.name,
					van: frm.doc.van,
					salesman: frm.doc.salesman,
					posting_date: frm.doc.trip_date,
				});
			}, __("Create")).addClass("btn-primary");
		}

		frm.add_custom_button(__("Van Stock"), () => {
			frappe.set_route("query-report", "Van Stock Position", { van: frm.doc.van });
		}, __("View"));
	},

	set_indicators(frm) {
		const map = {
			Draft: "red", Loaded: "orange", "In Progress": "blue",
			Returned: "purple", Closed: "green", Cancelled: "grey",
		};
		if (frm.doc.status) frm.page.set_indicator(__(frm.doc.status), map[frm.doc.status] || "grey");
	},

	van(frm) {
		if (!frm.doc.van) return;
		frappe.db.get_value("Van", frm.doc.van, ["warehouse", "salesman", "driver", "default_route"])
			.then((r) => {
				frm.set_value({
					van_warehouse: r.message.warehouse,
					salesman: r.message.salesman,
					driver: r.message.driver,
					route: frm.doc.route || r.message.default_route,
				});
			});
	},

	route(frm) {
		if (!frm.doc.route || (frm.doc.stops || []).length) return;
		frm.clear_table("stops");
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Van Route Stop",
				parent: "Van Route",
				filters: { parent: frm.doc.route },
				fields: ["customer", "customer_name", "sequence"],
				order_by: "sequence asc",
				limit_page_length: 0,
			},
			callback(r) {
				(r.message || []).forEach((s) => {
					frm.add_child("stops", { ...s, status: "Pending" });
				});
				frm.refresh_field("stops");
			},
		});
	},

	suggest_load(frm) {
		frappe.call({
			method: "neoaqua.neoaqua.doctype.van_load_request.van_load_request.get_suggested_load",
			args: { van: frm.doc.van, route: frm.doc.route },
			callback(r) {
				frm.clear_table("items");
				(r.message || []).forEach((row) => frm.add_child("items", {
					item_code: row.item_code, loaded_qty: row.qty,
				}));
				frm.refresh_field("items");
			},
		});
	},

	onload(frm) {
		frm.set_query("van", () => ({ filters: { status: "Active", company: frm.doc.company } }));
		if (frm.is_new()) {
			frm.add_custom_button(__("Suggest Load from History"), () => frm.trigger("suggest_load"));
		}
	},
});
