// Copyright (c) 2026, Neotec Integrated Solutions
/* NeoAqua Control Tower — one screen for the whole operation. */

frappe.pages["neoaqua-control-tower"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Control Tower"),
		single_column: true,
	});
	new ControlTower(page);
};

class ControlTower {
	constructor(page) {
		this.page = page;
		this.data = null;
		this.setup();
	}

	async setup() {
		this.build_toolbar();
		this.build_shell();
		await this.load();
		// A cockpit is left open, so keep it current without a click.
		this.timer = setInterval(() => this.load(true), 90000);
		$(this.page.wrapper).on("remove", () => clearInterval(this.timer));
	}

	// ------------------------------------------------------------ chrome
	build_toolbar() {
		this.date_field = this.page.add_field({
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			change: () => this.load(),
		});

		this.company_field = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			change: () => this.load(),
		});

		this.page.set_secondary_action(__("Refresh"), () => this.load(), "refresh");

		this.page.add_menu_item(__("NeoAqua Hub"), () => frappe.set_route("neoaqua-hub"));
		this.page.add_menu_item(__("New Van Trip"), () => frappe.new_doc("Van Trip"));
		this.page.add_menu_item(__("New Van Load Request"), () => frappe.new_doc("Van Load Request"));
		this.page.add_menu_item(__("New Work Order"), () => frappe.new_doc("Work Order"));
		this.page.add_menu_item(__("New Day Close"), () => frappe.new_doc("Salesman Day Close"));
		this.page.add_menu_item(__("Quality Check"), () => frappe.new_doc("Water Quality Check"));
		this.page.add_menu_item(__("Batch Code Builder"), () => frappe.set_route("batch-code-builder"));
		this.page.add_menu_item(__("Plant Setup"), () => frappe.set_route("Form", "NeoAqua Settings"));
		this.page.add_menu_item(__("Demo Data"), () => frappe.set_route("Form", "NeoAqua Demo Tool"));
	}

	build_shell() {
		this.page.main.html(`
			<div class="nact">
				<div id="nact-alert"></div>
				<div id="nact-kpis" class="nact-kpis"></div>
				<div id="nact-rails" class="nact-rails"></div>
				<div class="nact-split">
					<div class="nact-col-main">
						<div class="nact-panel">
							<div class="nact-panel-h">${__("Vans today")}</div>
							<div id="nact-vans"></div>
						</div>
						<div class="nact-panel">
							<div class="nact-panel-h">${__("Production lines — last 7 days")}</div>
							<div id="nact-lines"></div>
						</div>
					</div>
					<div class="nact-col-side">
						<div class="nact-panel">
							<div class="nact-panel-h">${__("Needs attention")}</div>
							<div id="nact-exceptions"></div>
						</div>
						<div class="nact-panel">
							<div class="nact-panel-h">${__("Sales — last 14 days")}</div>
							<div id="nact-trend"></div>
						</div>
					</div>
				</div>
			</div>
		`);
		this.inject_styles();
	}

	inject_styles() {
		if (document.getElementById("nact-styles")) return;
		$(`<style id="nact-styles">
		.nact { padding-bottom: 40px; }
		.nact-kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:16px; }
		.nact-kpi { background:var(--card-bg); border:1px solid var(--border-color);
			border-radius:8px; padding:11px 13px; border-left:3px solid #1B98E0; }
		.nact-kpi .l { font-size:10px; text-transform:uppercase; letter-spacing:.05em; color:var(--text-muted); }
		.nact-kpi .v { font-size:20px; font-weight:600; margin-top:3px; font-variant-numeric:tabular-nums; }
		.nact-kpi.good { border-left-color:var(--green-500); }
		.nact-kpi.bad  { border-left-color:var(--red-500); }
		.nact-kpi.warn { border-left-color:var(--orange-500); }
		.nact-kpi.info { border-left-color:var(--blue-500); }

		.nact-rails { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr));
			gap:10px; margin-bottom:16px; }
		.nact-rail { background:var(--card-bg); border:1px solid var(--border-color);
			border-radius:8px; overflow:hidden; }
		.nact-rail-h { background:linear-gradient(135deg,#13293D,#1B98E0); color:#fff;
			padding:9px 13px; font-size:12px; font-weight:600; display:flex; gap:8px; align-items:center; }
		.nact-step { display:flex; justify-content:space-between; align-items:center;
			padding:8px 13px; border-top:1px solid var(--border-color); cursor:pointer; font-size:12px; }
		.nact-step:first-of-type { border-top:none; }
		.nact-step:hover { background:var(--fg-hover-color,#f4f7f9); }
		.nact-step .n { font-weight:600; font-variant-numeric:tabular-nums; }
		.nact-step .n.zero { color:var(--text-muted); font-weight:400; }

		.nact-split { display:grid; grid-template-columns:2fr 1fr; gap:14px; }
		@media (max-width: 900px){ .nact-split{ grid-template-columns:1fr; } }
		.nact-panel { background:var(--card-bg); border:1px solid var(--border-color);
			border-radius:8px; margin-bottom:14px; overflow:hidden; }
		.nact-panel-h { padding:9px 13px; font-size:12px; font-weight:600;
			border-bottom:1px solid var(--border-color); }

		.nact-van { display:grid; grid-template-columns:1.3fr 1fr 1fr 1fr auto; gap:8px;
			align-items:center; padding:10px 13px; border-top:1px solid var(--border-color);
			font-size:12px; cursor:pointer; }
		.nact-van:hover { background:var(--fg-hover-color,#f4f7f9); }
		.nact-van .name { font-weight:600; }
		.nact-van .sub { font-size:11px; color:var(--text-muted); }
		.nact-bar { height:5px; background:var(--border-color); border-radius:3px; overflow:hidden; margin-top:4px; }
		.nact-bar > i { display:block; height:100%; background:#1B98E0; }

		.nact-exc { display:flex; gap:9px; align-items:flex-start; padding:9px 13px;
			border-top:1px solid var(--border-color); cursor:pointer; font-size:12px; }
		.nact-exc:hover { background:var(--fg-hover-color,#f4f7f9); }
		.nact-exc .dot { width:8px; height:8px; border-radius:50%; margin-top:5px; flex:none; }
		.nact-exc .dot.high{background:var(--red-500)} .nact-exc .dot.medium{background:var(--orange-500)}
		.nact-exc .dot.low{background:var(--blue-400,#7cc4f0)}
		.nact-exc .c { margin-left:auto; font-weight:600; font-variant-numeric:tabular-nums; }
		.nact-exc .hint { font-size:11px; color:var(--text-muted); }

		.nact-empty { padding:22px 13px; text-align:center; color:var(--text-muted); font-size:12px; }
		.nact-spark { display:flex; align-items:flex-end; gap:3px; height:80px; padding:14px 13px 8px; }
		.nact-spark > i { flex:1; background:#1B98E0; border-radius:2px 2px 0 0; min-height:2px; opacity:.85; }
		.nact-spark > i:last-child { background:#13293D; opacity:1; }
		.nact-spark-f { display:flex; justify-content:space-between; padding:0 13px 10px;
			font-size:10px; color:var(--text-muted); }
		</style>`).appendTo("head");
	}

	// ------------------------------------------------------------ data
	async load(silent) {
		if (!silent) this.page.main.find("#nact-alert").html("");
		try {
			const r = await frappe.call({
				method: "neoaqua.api.control_tower.get_overview",
				args: {
					company: this.company_field.get_value(),
					date: this.date_field.get_value(),
				},
			});
			this.data = r.message || {};
			this.render();
		} catch (e) {
			this.page.main.find("#nact-alert").html(
				`<div class="alert alert-danger">${__("Could not load the overview.")}</div>`
			);
		}
	}

	render() {
		const d = this.data;
		if (d.error) {
			$("#nact-alert").html(`<div class="alert alert-warning">${frappe.utils.escape_html(d.error)}</div>`);
			return;
		}
		this.render_alert(d);
		this.render_kpis(d.panels.kpis || []);
		this.render_rails(d.panels.pipeline || []);
		this.render_vans(d.panels.vans || []);
		this.render_lines(d.panels.lines || []);
		this.render_exceptions(d.panels.exceptions || []);
		this.render_trend(d.panels.trend || []);
	}

	render_alert(d) {
		let html = "";
		if (d.setup_complete === false) {
			html += `<div class="alert alert-warning" style="display:flex;gap:10px;align-items:center">
				<div style="flex:1"><b>${__("The plant is not fully set up.")}</b>
				${__("{0} checks are failing, so these numbers will be incomplete.", [
					(d.setup_missing || []).length,
				])}</div>
				<button class="btn btn-sm btn-primary" id="nact-go-setup">${__("Open setup")}</button>
			</div>`;
		}
		const errs = Object.keys(d.errors || {});
		if (errs.length) {
			html += `<div class="alert alert-danger" style="font-size:12px">
				${__("Some panels could not be built:")} ${frappe.utils.escape_html(errs.join(", "))}</div>`;
		}
		$("#nact-alert").html(html);
		$("#nact-go-setup").on("click", () => frappe.set_route("Form", "NeoAqua Settings"));
	}

	fmt(v, kind) {
		if (v === null || v === undefined) return "—";
		if (kind === "currency") return format_currency(v, "SAR", 0);
		if (kind === "percent") return `${Math.round(v)}%`;
		return frappe.utils.shorten_number ? frappe.utils.shorten_number(v) : Math.round(v).toLocaleString();
	}

	render_kpis(kpis) {
		$("#nact-kpis").html(
			kpis
				.map(
					(k) => `<div class="nact-kpi ${k.tone || ""}">
						<div class="l">${frappe.utils.escape_html(k.label)}</div>
						<div class="v">${this.fmt(k.value, k.fmt)}</div>
					</div>`
				)
				.join("")
		);
	}

	render_rails(stages) {
		const html = stages
			.map(
				(s, si) => `<div class="nact-rail">
					<div class="nact-rail-h"><span>${s.icon}</span>${frappe.utils.escape_html(s.label)}</div>
					${s.steps
						.map(
							(st, i) => `<div class="nact-step" data-stage="${si}" data-step="${i}">
								<span>${frappe.utils.escape_html(st.label)}</span>
								<span class="n ${st.count ? "" : "zero"}">${
									st.is_qty ? this.fmt(st.count, "number") : st.count
								}</span>
							</div>`
						)
						.join("")}
				</div>`
			)
			.join("");
		$("#nact-rails").html(html);

		$("#nact-rails .nact-step").on("click", (e) => {
			const s = stages[+$(e.currentTarget).data("stage")];
			const step = s.steps[+$(e.currentTarget).data("step")];
			if (step.route) frappe.set_route(...step.route);
		});
	}

	render_vans(vans) {
		if (!vans.length) {
			$("#nact-vans").html(`<div class="nact-empty">${__("No active vans.")}</div>`);
			return;
		}
		const pill = {
			idle: ["grey", __("Idle")],
			loaded: ["orange", __("Loaded")],
			running: ["blue", __("On route")],
			awaiting_close: ["purple", __("Awaiting day close")],
			closed: ["green", __("Settled")],
		};
		$("#nact-vans").html(
			vans
				.map((v) => {
					const [colour, label] = pill[v.state] || pill.idle;
					return `<div class="nact-van" data-trip="${v.trip || ""}" data-van="${frappe.utils.escape_html(v.van)}">
						<div>
							<div class="name">${frappe.utils.escape_html(v.van)}</div>
							<div class="sub">${frappe.utils.escape_html(v.salesman || __("Unassigned"))}</div>
						</div>
						<div>
							<span class="indicator-pill ${colour}">${label}</span>
						</div>
						<div>
							<div class="sub">${__("Coverage")} ${Math.round(v.coverage)}% · ${v.visited}/${v.planned}</div>
							<div class="nact-bar"><i style="width:${Math.min(v.coverage, 100)}%"></i></div>
						</div>
						<div>
							<div class="sub">${__("Invoiced")} ${format_currency(v.invoiced, "SAR", 0)}</div>
							<div class="sub">${__("Collected")} ${format_currency(v.collected, "SAR", 0)}</div>
						</div>
						<div class="sub">${__("Stock")} ${format_currency(v.stock_value, "SAR", 0)}</div>
					</div>`;
				})
				.join("")
		);

		$("#nact-vans .nact-van").on("click", (e) => {
			const trip = $(e.currentTarget).data("trip");
			const van = $(e.currentTarget).data("van");
			if (trip) frappe.set_route("Form", "Van Trip", trip);
			else frappe.set_route("Form", "Van", van);
		});
	}

	render_lines(lines) {
		if (!lines.length) {
			$("#nact-lines").html(`<div class="nact-empty">${__("No work orders in the last seven days.")}</div>`);
			return;
		}
		$("#nact-lines").html(
			lines
				.map((l) => {
					const a = Math.round(l.attainment);
					const colour = a >= 97 ? "var(--green-500)" : a >= 85 ? "var(--orange-500)" : "var(--red-500)";
					return `<div class="nact-van" style="grid-template-columns:1.4fr 1fr 1fr auto">
						<div><div class="name">${frappe.utils.escape_html(l.line)}</div>
							<div class="sub">${l.orders} ${__("work orders")}</div></div>
						<div class="sub">${__("Planned")} ${Math.round(l.planned).toLocaleString()}</div>
						<div class="sub">${__("Produced")} ${Math.round(l.produced).toLocaleString()}</div>
						<div style="min-width:90px">
							<div class="sub">${__("Attainment")} ${a}%</div>
							<div class="nact-bar"><i style="width:${Math.min(a, 100)}%;background:${colour}"></i></div>
						</div>
					</div>`;
				})
				.join("")
		);
	}

	render_exceptions(items) {
		if (!items.length) {
			$("#nact-exceptions").html(
				`<div class="nact-empty">${__("Nothing needs attention. Good.")}</div>`
			);
			return;
		}
		$("#nact-exceptions").html(
			items
				.map(
					(x, i) => `<div class="nact-exc" data-i="${i}">
						<span class="dot ${x.severity}"></span>
						<span>
							${frappe.utils.escape_html(x.label)}
							${x.hint ? `<div class="hint">${frappe.utils.escape_html(x.hint)}</div>` : ""}
						</span>
						<span class="c">${x.count}</span>
					</div>`
				)
				.join("")
		);
		$("#nact-exceptions .nact-exc").on("click", (e) => {
			const x = items[+$(e.currentTarget).data("i")];
			if (x.route) frappe.set_route(...x.route);
		});
	}

	render_trend(series) {
		const max = Math.max(...series.map((s) => s.value), 1);
		$("#nact-trend").html(`
			<div class="nact-spark">
				${series
					.map(
						(s) =>
							`<i style="height:${Math.max((s.value / max) * 100, 2)}%"
								title="${s.date}: ${format_currency(s.value, "SAR", 0)}"></i>`
					)
					.join("")}
			</div>
			<div class="nact-spark-f">
				<span>${series.length ? series[0].date.slice(5) : ""}</span>
				<span>${__("peak")} ${format_currency(max, "SAR", 0)}</span>
				<span>${series.length ? series[series.length - 1].date.slice(5) : ""}</span>
			</div>
		`);
	}
}
