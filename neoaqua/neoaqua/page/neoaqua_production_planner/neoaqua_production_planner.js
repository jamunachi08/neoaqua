// Copyright (c) 2026, Neotec Integrated Solutions
/* Dynamic production planner. Every demand signal is a toggle, because they
   disagree and the planner's job is to show the disagreement. */

frappe.pages["neoaqua-production-planner"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Production Planner"),
		single_column: true,
	});
	new ProductionPlanner(page);
};

class ProductionPlanner {
	constructor(page) {
		this.page = page;
		this.edits = {};
		this.setup();
	}

	setup() {
		this.build_filters();
		this.inject_styles();
		this.page.main.html(`
			<div class="npp">
				<div id="npp-toggles" class="npp-toggles"></div>
				<div id="npp-summary"></div>
				<div id="npp-capacity"></div>
				<div id="npp-table"></div>
				<div id="npp-shortfall"></div>
			</div>`);
		this.render_toggles();
		this.page.set_primary_action(__("Create Production Plan"), () => this.create_plan(), "add");
		this.page.set_secondary_action(__("Refresh"), () => this.load(), "refresh");
		this.page.add_menu_item(__("Check Material Shortfall"), () => this.load_shortfall());
		this.load();
	}

	build_filters() {
		const today = frappe.datetime.get_today();
		this.f = {};
		const add = (spec) => (this.f[spec.fieldname] = this.page.add_field(spec));

		add({ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		      default: frappe.defaults.get_user_default("Company"), change: () => this.load() });
		add({ fieldname: "from_date", label: __("Plan From"), fieldtype: "Date",
		      default: today, change: () => this.load() });
		add({ fieldname: "to_date", label: __("Plan To"), fieldtype: "Date",
		      default: frappe.datetime.add_days(today, 30), change: () => this.load() });
		add({ fieldname: "production_line", label: __("Line"), fieldtype: "Select",
		      options: ["", "Line 1 - Small PET", "Line 2 - Large PET", "Line 3 - 5 Gallon", "RO Plant"],
		      change: () => this.load() });
		add({ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link",
		      options: "Item Group", change: () => this.load() });
	}

	// ------------------------------------------------------------ toggles
	render_toggles() {
		this.opts = {
			show_history: 1, history_months: 3,
			show_last_year: 0, show_open_orders: 1, show_wip: 1, show_stock: 1,
			apply_seasonality: 0, show_capacity: 1,
			safety_days: 7, round_to_batch: 1, include_sub_assemblies: 0,
		};

		const checks = [
			["show_history", __("Previous months sales"), __("Trailing sales history and the daily run rate")],
			["show_last_year", __("Same period last year"), __("Blends last year's window into the forecast — the only signal that knows about the season")],
			["show_open_orders", __("Current sales orders"), __("Demand already committed but not delivered")],
			["show_wip", __("Under production"), __("Work orders submitted and not yet finished")],
			["show_stock", __("Stock on hand"), __("Finished goods in the plant and on the vans")],
			["apply_seasonality", __("Seasonality factor"), __("Applies a KSA monthly demand curve — summer peak, winter trough")],
			["show_capacity", __("Capacity check"), __("Compares required routing minutes with the lines' available hours")],
			["round_to_batch", __("Round to whole batches"), __("Rounds up to a whole BOM batch")],
			["include_sub_assemblies", __("Include sub-assemblies"), __("Plan WIP items as well as finished goods")],
		];

		const nums = [
			["history_months", __("History months"), 1, 24],
			["safety_days", __("Safety stock days"), 0, 60],
		];

		$("#npp-toggles").html(`
			<div class="npp-tg-h">${__("Signals")}
				<span class="npp-tg-s">${__("Switch a signal off to see how much it was driving the plan")}</span></div>
			<div class="npp-tg-body">
				${checks
					.map(
						([k, label, hint]) => `
					<label class="npp-tg" title="${frappe.utils.escape_html(hint)}">
						<input type="checkbox" data-opt="${k}" ${this.opts[k] ? "checked" : ""}>
						<span>${label}</span>
					</label>`
					)
					.join("")}
				${nums
					.map(
						([k, label, min, max]) => `
					<label class="npp-tg npp-num">
						<span>${label}</span>
						<input type="number" data-num="${k}" value="${this.opts[k]}" min="${min}" max="${max}">
					</label>`
					)
					.join("")}
			</div>`);

		$("#npp-toggles [data-opt]").on("change", (e) => {
			this.opts[$(e.currentTarget).data("opt")] = e.currentTarget.checked ? 1 : 0;
			this.load();
		});
		$("#npp-toggles [data-num]").on("change", (e) => {
			this.opts[$(e.currentTarget).data("num")] = cint(e.currentTarget.value);
			this.load();
		});
	}

	filters() {
		const out = { ...this.opts };
		Object.keys(this.f).forEach((k) => (out[k] = this.f[k].get_value()));
		return out;
	}

	// ------------------------------------------------------------ load
	load() {
		this.edits = {};
		frappe.call({
			method: "neoaqua.api.production_planner.get_plan",
			args: { filters: this.filters() },
			freeze: true,
			freeze_message: __("Building the plan..."),
			callback: (r) => {
				this.data = r.message || {};
				this.render();
			},
		});
	}

	render() {
		const d = this.data;
		if (d.message) {
			$("#npp-table").html(`<div class="npp-empty">${frappe.utils.escape_html(d.message)}</div>`);
			$("#npp-summary,#npp-capacity,#npp-shortfall").empty();
			return;
		}
		this.render_summary(d);
		this.render_capacity(d);
		this.render_table(d);
		$("#npp-shortfall").empty();
	}

	render_summary(d) {
		const t = d.totals || {};
		const tile = (l, v, tone) =>
			`<div class="npp-kpi ${tone || ""}"><div class="l">${l}</div><div class="v">${v}</div></div>`;
		$("#npp-summary").html(`
			<div class="npp-kpis">
				${tile(__("Horizon"), `${d.horizon_days} ${__("days")}`)}
				${tile(__("Items to produce"), t.items || 0)}
				${tile(__("Suggested quantity"), Math.round(t.to_produce || 0).toLocaleString(), "good")}
				${tile(__("Committed orders"), Math.round(t.open_orders || 0).toLocaleString())}
				${tile(__("Already in production"), Math.round(t.under_production || 0).toLocaleString())}
				${tile(__("Stock on hand"), Math.round(t.stock_total || 0).toLocaleString())}
				${
					d.show.seasonality
						? tile(__("Season ({0})", [d.season_month]), `×${d.season_factor.toFixed(2)}`, "info")
						: ""
				}
			</div>`);
	}

	render_capacity(d) {
		if (!d.show.capacity || !(d.capacity || []).length) return $("#npp-capacity").empty();
		$("#npp-capacity").html(`
			<div class="npp-sec">${__("Line capacity over the horizon")}</div>
			<div class="npp-cap">
				${d.capacity
					.map((c) => {
						const u = Math.round(c.utilisation);
						const tone = u > 100 ? "bad" : u > 85 ? "warn" : "good";
						return `<div class="npp-cap-row">
							<div class="n">${frappe.utils.escape_html(c.line)}</div>
							<div class="b"><i class="${tone}" style="width:${Math.min(u, 100)}%"></i></div>
							<div class="v ${tone}">${u}%</div>
							<div class="s">${c.required_hours}h / ${c.available_hours}h</div>
						</div>`;
					})
					.join("")}
			</div>
			${
				d.capacity.some((c) => c.utilisation > 100)
					? `<div class="npp-warn">${__(
							"At least one line is over capacity. Extend the horizon, move volume to another line, or cut the plan — the lines cannot run what is being asked."
					  )}</div>`
					: ""
			}`);
	}

	render_table(d) {
		const periods = d.periods || [];
		const show = d.show;

		const head = [
			`<th class="l">${__("Item")}</th>`,
			show.history ? periods.map((p) => `<th class="r">${p.slice(2)}</th>`).join("") : "",
			show.history ? `<th class="r">${__("Avg/mo")}</th>` : "",
			show.last_year ? `<th class="r">${__("LY same")}</th><th class="r">${__("YoY")}</th>` : "",
			show.open_orders ? `<th class="r">${__("Orders")}</th>` : "",
			show.wip ? `<th class="r">${__("In prod")}</th>` : "",
			show.stock ? `<th class="r">${__("Plant")}</th><th class="r">${__("Van")}</th>` : "",
			`<th class="r">${__("Forecast")}</th>`,
			`<th class="r">${__("Suggested")}</th>`,
			`<th class="r">${__("Cover")}</th>`,
		].join("");

		const body = (d.rows || [])
			.map((r, i) => {
				const cells = [
					`<td class="l"><b>${frappe.utils.escape_html(r.item_code)}</b>
						<div class="sub">${frappe.utils.escape_html(r.item_name || "")}</div></td>`,
					show.history ? periods.map((p) => `<td class="r">${Math.round(r.history[p] || 0)}</td>`).join("") : "",
					show.history ? `<td class="r">${Math.round(r.avg_monthly)}</td>` : "",
					show.last_year
						? `<td class="r">${Math.round(r.last_year)}</td>
						   <td class="r ${r.yoy_pct === null ? "" : r.yoy_pct >= 0 ? "up" : "down"}">${
								r.yoy_pct === null ? "—" : Math.round(r.yoy_pct) + "%"
						   }</td>`
						: "",
					show.open_orders ? `<td class="r">${Math.round(r.open_orders)}</td>` : "",
					show.wip ? `<td class="r">${Math.round(r.under_production)}</td>` : "",
					show.stock
						? `<td class="r">${Math.round(r.stock_plant)}</td><td class="r">${Math.round(r.stock_van)}</td>`
						: "",
					`<td class="r">${Math.round(r.forecast)}</td>`,
					`<td class="r"><input class="npp-qty" data-row="${i}" type="number" min="0"
						value="${Math.round(r.suggested_qty)}"></td>`,
					`<td class="r sub">${
						r.days_cover_after === null ? "—" : Math.round(r.days_cover_after) + "d"
					}${r.capped_by_shelf_life ? ' <span title="' + __("Capped by shelf life") + '">&#9888;</span>' : ""}</td>`,
				].join("");
				return `<tr>${cells}</tr>`;
			})
			.join("");

		$("#npp-table").html(`
			<div class="npp-sec">${__("The plan")}
				<span class="npp-tg-s">${__("Suggested quantities are editable before you create the plan")}</span></div>
			<div class="npp-wrap">
				<table class="npp-t"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
			</div>`);

		$(".npp-qty").on("change", (e) => {
			const i = +$(e.currentTarget).data("row");
			this.data.rows[i].suggested_qty = flt(e.currentTarget.value);
		});
	}

	// ------------------------------------------------------------ shortfall
	load_shortfall() {
		frappe.call({
			method: "neoaqua.api.production_planner.get_shortfall",
			args: { rows: this.data.rows, company: this.f.company.get_value() },
			freeze: true,
			freeze_message: __("Exploding the BOM tree..."),
			callback: (r) => {
				const rows = r.message || [];
				if (!rows.length) {
					$("#npp-shortfall").html(`<div class="npp-empty">${__("Nothing to explode — set some quantities first.")}</div>`);
					return;
				}
				const short = rows.filter((x) => x.shortfall > 0);
				$("#npp-shortfall").html(`
					<div class="npp-sec">${__("Material requirement")}
						<span class="npp-tg-s">${__("{0} of {1} raw materials fall short", [short.length, rows.length])}</span></div>
					<div class="npp-wrap">
						<table class="npp-t"><thead><tr>
							<th class="l">${__("Item")}</th><th class="r">${__("Required")}</th>
							<th class="r">${__("In stock")}</th><th class="r">${__("On order")}</th>
							<th class="r">${__("Shortfall")}</th></tr></thead>
						<tbody>${rows
							.map(
								(x) => `<tr class="${x.shortfall > 0 ? "npp-short" : ""}">
									<td class="l">${frappe.utils.escape_html(x.item_code)}
										<div class="sub">${frappe.utils.escape_html(x.item_name || "")}</div></td>
									<td class="r">${Math.round(x.required)}</td>
									<td class="r">${Math.round(x.in_stock)}</td>
									<td class="r">${Math.round(x.on_order)}</td>
									<td class="r"><b>${x.shortfall > 0 ? Math.round(x.shortfall) : "—"}</b></td>
								</tr>`
							)
							.join("")}</tbody></table>
					</div>
					${short.length ? `<button class="btn btn-sm btn-default" id="npp-mr">${__("Raise Material Request for the shortfall")}</button>` : ""}
				`);
				$("#npp-mr").on("click", () => {
					frappe.call({
						method: "neoaqua.api.production_planner.create_material_requests",
						args: { shortfall: rows, company: this.f.company.get_value() },
						callback: (res) => {
							const m = res.message || {};
							frappe.msgprint({
								title: __("Material Request created"),
								indicator: "green",
								message: __("Draft {0} with {1} lines.", [m.material_request, m.items]),
							});
							frappe.set_route("Form", "Material Request", m.material_request);
						},
					});
				});
			},
		});
	}

	create_plan() {
		const rows = (this.data.rows || []).filter((r) => flt(r.suggested_qty) > 0);
		if (!rows.length) {
			frappe.msgprint(__("Every suggested quantity is zero — nothing to plan."));
			return;
		}
		frappe.confirm(
			__("Create a draft Production Plan for {0} items?", [rows.length]),
			() => {
				frappe.call({
					method: "neoaqua.api.production_planner.create_production_plan",
					args: {
						rows: rows,
						company: this.f.company.get_value(),
						from_date: this.f.from_date.get_value(),
						to_date: this.f.to_date.get_value(),
					},
					freeze: true,
					callback: (r) => {
						const m = r.message || {};
						frappe.show_alert({ message: __("Draft {0} created", [m.production_plan]), indicator: "green" });
						frappe.set_route("Form", "Production Plan", m.production_plan);
					},
				});
			}
		);
	}

	// ------------------------------------------------------------ styles
	inject_styles() {
		if (document.getElementById("npp-styles")) return;
		$(`<style id="npp-styles">
		.npp { padding-bottom:48px; }
		.npp-toggles { background:var(--card-bg); border:1px solid var(--border-color);
			border-radius:9px; padding:11px 14px; margin-bottom:14px; }
		.npp-tg-h { font-size:12px; font-weight:600; margin-bottom:9px; }
		.npp-tg-s { font-weight:400; color:var(--text-muted); margin-left:8px; }
		.npp-tg-body { display:flex; flex-wrap:wrap; gap:8px 18px; }
		.npp-tg { display:flex; gap:6px; align-items:center; font-size:12px;
			font-weight:400; margin:0; cursor:pointer; }
		.npp-num input { width:62px; font-size:12px; padding:2px 6px;
			border:1px solid var(--border-color); border-radius:4px; }
		.npp-kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(135px,1fr));
			gap:9px; margin-bottom:14px; }
		.npp-kpi { background:var(--card-bg); border:1px solid var(--border-color);
			border-left:3px solid #1B98E0; border-radius:8px; padding:9px 12px; }
		.npp-kpi.good { border-left-color:var(--green-500,#10B981); }
		.npp-kpi.info { border-left-color:var(--purple-500,#8B5CF6); }
		.npp-kpi .l { font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-muted); }
		.npp-kpi .v { font-size:18px; font-weight:600; margin-top:2px; }
		.npp-sec { font-size:12px; font-weight:600; margin:18px 0 8px; }
		.npp-cap { background:var(--card-bg); border:1px solid var(--border-color); border-radius:8px; }
		.npp-cap-row { display:grid; grid-template-columns:1.4fr 3fr 60px 120px; gap:10px;
			align-items:center; padding:8px 13px; border-top:1px solid var(--border-color); font-size:12px; }
		.npp-cap-row:first-child { border-top:none; }
		.npp-cap-row .b { background:var(--border-color); height:7px; border-radius:4px; overflow:hidden; }
		.npp-cap-row .b i { display:block; height:100%; }
		.npp-cap-row .b i.good{background:var(--green-500,#10B981)}
		.npp-cap-row .b i.warn{background:var(--orange-500,#F59E0B)}
		.npp-cap-row .b i.bad{background:var(--red-500,#EF4444)}
		.npp-cap-row .v.bad{color:var(--red-600)} .npp-cap-row .v.warn{color:var(--orange-600)}
		.npp-cap-row .s { color:var(--text-muted); text-align:right; }
		.npp-warn { background:#FEF3C7; border:1px solid #FCD34D; border-radius:7px;
			padding:9px 12px; font-size:12px; margin-top:9px; }
		.npp-wrap { overflow-x:auto; border:1px solid var(--border-color); border-radius:8px; }
		.npp-t { width:100%; border-collapse:collapse; font-size:12px; background:var(--card-bg); }
		.npp-t th { background:var(--fg-color,#f8fafc); padding:7px 9px; font-weight:600;
			border-bottom:1px solid var(--border-color); white-space:nowrap; font-size:11px; }
		.npp-t td { padding:6px 9px; border-bottom:1px solid var(--border-color); white-space:nowrap; }
		.npp-t .l { text-align:left; } .npp-t .r { text-align:right; }
		.npp-t .sub { font-size:10px; color:var(--text-muted); font-weight:400; }
		.npp-t .up { color:var(--green-600); } .npp-t .down { color:var(--red-600); }
		.npp-qty { width:82px; text-align:right; font-size:12px; padding:2px 6px;
			border:1px solid var(--border-color); border-radius:4px; }
		.npp-short { background:#FEF2F2; }
		.npp-empty { padding:34px; text-align:center; color:var(--text-muted); font-size:12px; }
		</style>`).appendTo("head");
	}
}
