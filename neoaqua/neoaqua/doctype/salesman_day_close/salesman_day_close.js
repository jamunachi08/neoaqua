// Copyright (c) 2026, Neotec Integrated Solutions
frappe.ui.form.on("Salesman Day Close", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.van_trip) {
			frm.add_custom_button(__("Fetch Trip Activity"), () => {
				frappe.show_alert({ message: __("Pulling invoices, collections and load sheet..."), indicator: "blue" });
				frm.call("fetch_trip_activity").then(() => frm.reload_doc());
			}).addClass("btn-primary");
		}

		if (frm.doc.docstatus === 1) {
			if (frm.doc.journal_entry) {
				frm.add_custom_button(__("Cash Journal"), () =>
					frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry), __("View"));
			}
			if (frm.doc.return_stock_entry) {
				frm.add_custom_button(__("Return Entry"), () =>
					frappe.set_route("Form", "Stock Entry", frm.doc.return_stock_entry), __("View"));
			}
		}

		frm.trigger("render_variance_banner");
	},

	render_variance_banner(frm) {
		frm.dashboard.clear_headline();
		if (!frm.doc.declared_cash) return;
		const v = flt(frm.doc.cash_variance);
		if (Math.abs(v) < 0.005) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill green">${__("Cash reconciled exactly")}</span>`);
		} else {
			const label = v < 0 ? __("Short by") : __("Excess of");
			frm.dashboard.set_headline(
				`<span class="indicator-pill ${v < 0 ? "red" : "blue"}">${label} ${format_currency(Math.abs(v), "SAR")}</span>`);
		}
	},

	declared_cash(frm) { frm.trigger("render_variance_banner"); },
	opening_float(frm) { frm.trigger("render_variance_banner"); },

	van_trip(frm) {
		if (!frm.doc.van_trip) return;
		frappe.db.get_value("Van Trip", frm.doc.van_trip, ["van", "salesman", "route", "trip_date"])
			.then((r) => frm.set_value({
				van: r.message.van,
				salesman: r.message.salesman,
				route: r.message.route,
				posting_date: r.message.trip_date,
			}));
	},

	onload(frm) {
		frm.set_query("van_trip", () => ({
			filters: { docstatus: 1, status: ["in", ["Loaded", "In Progress", "Returned"]] },
		}));
		frm.set_query("deposit_account", () => ({
			filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Cash", "Bank"]] },
		}));
	},
});

frappe.ui.form.on("Day Close Expense", {
	expense_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.expense_type || row.expense_account) return;
		frappe.call({
			method: "neoaqua.setup.accounts.get_expense_account",
			args: { expense_type: row.expense_type },
			callback(r) {
				if (r.message) frappe.model.set_value(cdt, cdn, "expense_account", r.message);
			},
		});
	},
});

frappe.ui.form.on("Day Close Stock Item", {
	returned_qty(frm) { frm.script_manager.trigger("validate"); },
	damaged_qty(frm) { frm.script_manager.trigger("validate"); },
});
