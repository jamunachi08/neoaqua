// Copyright (c) 2026, Neotec Integrated Solutions
/* NeoAqua Hub — the master workspace.
   Everything rendered here was already filtered server-side by permission;
   the client draws what it is given and never decides who sees what. */

frappe.pages["neoaqua-hub"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("NeoAqua"),
		single_column: true,
	});
	new NeoAquaHub(page);
};

class NeoAquaHub {
	constructor(page) {
		this.page = page;
		this.setup();
	}

	async setup() {
		this.page.set_secondary_action(__("Refresh"), () => this.load(), "refresh");
		this.page.add_menu_item(__("Control Tower"), () => frappe.set_route("neoaqua-control-tower"));
		this.page.add_menu_item(__("Settings"), () => frappe.set_route("Form", "NeoAqua Settings"));
		this.inject_styles();
		this.page.main.html(`<div class="nah"><div id="nah-body"></div></div>`);
		await this.load();
	}

	async load() {
		const r = await frappe.call({ method: "neoaqua.api.hub.get_hub" });
		this.data = r.message || {};
		this.render();
	}

	// ------------------------------------------------------------ render
	render() {
		const d = this.data;
		$("#nah-body").html(`
			${this.hero(d)}
			${d.setup_complete === false ? this.setup_banner(d) : ""}
			${d.my_work.length ? this.my_work(d.my_work) : ""}
			${d.lanes.length ? this.flow(d.lanes) : ""}
			${d.tiles.length ? this.tiles(d.tiles) : ""}
			${!d.lanes.length && !d.tiles.length ? this.nothing() : ""}
		`);
		this.bind();
	}

	hero(d) {
		const hour = new Date().getHours();
		const greet = hour < 12 ? __("Good morning") : hour < 18 ? __("Good afternoon") : __("Good evening");
		// only use a first name when it actually looks like one
		const full = (d.user.full_name || "").trim();
		const looks_like_a_name = full && full.includes(" ") && !full.includes("@");
		const who = looks_like_a_name ? ", " + frappe.utils.escape_html(full.split(" ")[0]) : "";
		const actions = (d.actions || [])
			.map(
				(a) => `<button class="nah-act" data-new="${frappe.utils.escape_html(a.doctype)}">
					<span>${a.icon}</span>${frappe.utils.escape_html(a.label)}</button>`
			)
			.join("");
		return `
			<div class="nah-hero">
				<div class="nah-hero-t">
					<div style="display:flex;gap:14px;align-items:center">
						<img src="/assets/neoaqua/images/neoaqua-logo.svg" alt="" class="nah-logo">
					<div>
						<div class="nah-greet">${greet}${who}</div>
						<div class="nah-sub">
							${frappe.utils.escape_html(d.brand || "NeoAqua")}
							<span class="nah-chip">${frappe.utils.escape_html(d.persona.label)}</span>
						</div>
					</div></div>
					<div class="nah-date">${frappe.datetime.str_to_user(frappe.datetime.get_today())}</div>
				</div>
				${actions ? `<div class="nah-acts">${actions}</div>` : ""}
			</div>`;
	}

	setup_banner(d) {
		const missing = d.setup_missing || [];
		// Name what is missing, with the numbers. "Item master, BOMs or accounts
		// are missing" tells someone standing in front of it nothing actionable.
		const list = missing
			.slice(0, 8)
			.map(
				(m) => `<span class="nah-miss">${frappe.utils.escape_html(m.check)}
					<b>${m.actual}</b>/${m.expected}</span>`
			)
			.join("");
		return `<div class="nah-banner">
			<div style="flex:1 1 100%">
				<b>${__("The plant is not fully set up.")}</b>
				${__("{0} of the setup checks are short, so the figures below are incomplete.", [missing.length])}
				<div class="nah-misses">${list}${
					missing.length > 8
						? `<span class="nah-miss">+${missing.length - 8} ${__("more")}</span>`
						: ""
				}</div>
			</div>
			<div style="display:flex;gap:8px;margin-left:auto">
				${d.setup_can_fix ? `<button class="btn btn-sm btn-primary" id="nah-fix">${__("Create what is missing")}</button>` : ""}
				<button class="btn btn-sm btn-default" id="nah-setup">${__("Open setup")}</button>
			</div>
		</div>`;
	}

	my_work(items) {
		return `
			<div class="nah-sec-h">${__("Your work")}</div>
			<div class="nah-work">
				${items
					.map(
						(w, i) => `<div class="nah-w ${w.tone || ""}" data-work="${i}">
							<div class="nah-w-l">${frappe.utils.escape_html(w.label)}</div>
							<div class="nah-w-v">${frappe.utils.escape_html(String(w.value))}</div>
							${w.sub ? `<div class="nah-w-s">${frappe.utils.escape_html(w.sub)}</div>` : ""}
						</div>`
					)
					.join("")}
			</div>`;
	}

	flow(lanes) {
		return `
			<div class="nah-sec-h">${__("The process")}
				<span class="nah-sec-s">${__("Click any step to open it")}</span></div>
			<div class="nah-flow">
				${lanes
					.map(
						(lane, li) => `
					<div class="nah-lane" style="--lc:${lane.colour}">
						<div class="nah-lane-h"><span>${lane.icon}</span>${frappe.utils.escape_html(lane.label)}</div>
						<div class="nah-nodes">
							${lane.nodes
								.map(
									(n, ni) => `
								<div class="nah-node" data-lane="${li}" data-node="${ni}" title="${frappe.utils.escape_html(n.hint || "")}">
									<div class="nah-node-l">${frappe.utils.escape_html(n.label)}</div>
									${
										n.count === null || n.count === undefined
											? ""
											: `<div class="nah-node-c ${n.count ? "hot" : ""}">${n.count}</div>`
									}
								</div>`
								)
								.join('<div class="nah-arrow"><i></i></div>')}
						</div>
					</div>`
					)
					.join('<div class="nah-lane-link"><i></i></div>')}
			</div>`;
	}

	tiles(tiles) {
		return `
			<div class="nah-sec-h">${__("Everything else")}</div>
			<div class="nah-tiles">
				${tiles
					.map(
						(t, ti) => `
					<div class="nah-tile" style="--tc:${t.colour}">
						<div class="nah-tile-h"><span class="nah-tile-i">${t.icon}</span>${frappe.utils.escape_html(t.label)}</div>
						<div class="nah-tile-links">
							${t.links
								.map(
									(l, li) =>
										`<a class="nah-link" data-tile="${ti}" data-link="${li}">${frappe.utils.escape_html(l.label)}</a>`
								)
								.join("")}
						</div>
					</div>`
					)
					.join("")}
			</div>`;
	}

	nothing() {
		return `<div class="nah-none">
			<p>${__("You do not have access to any NeoAqua area yet.")}</p>
			<p class="text-muted">${__("Ask an administrator to assign you a role such as Van Salesman, Plant Operator or QC Inspector.")}</p>
		</div>`;
	}

	// ------------------------------------------------------------ events
	bind() {
		const d = this.data;

		$("#nah-setup").on("click", () => frappe.set_route("Form", "NeoAqua Settings"));

		$("#nah-fix").on("click", () => {
			frappe.confirm(
				__("This creates the item master, chart of accounts, BOM tree, vans and routes that are missing. Existing records are left alone. Continue?"),
				() => {
					frappe.call({
						method: "neoaqua.api.hub.run_setup_from_hub",
						args: { company: this.data.company },
						freeze: true,
						freeze_message: __("Setting up the plant. This takes a minute..."),
						callback: (r) => {
							const rep = r.message || {};
							const rows = (rep.stages || [])
								.map((s) => {
									const c = { Done: "green", Failed: "red", Skipped: "orange" }[s.status] || "grey";
									return `<tr><td><span class="indicator-pill ${c}">${s.status}</span></td>
										<td>${frappe.utils.escape_html(s.label)}</td>
										<td style="font-size:11px;color:var(--text-muted)">${frappe.utils.escape_html(
											s.error || s.detail || (s.result ? JSON.stringify(s.result) : "")
										)}</td></tr>`;
								})
								.join("");
							frappe.msgprint({
								title: rep.ok ? __("Setup Complete") : __("Setup Finished with Problems"),
								indicator: rep.ok ? "green" : "orange",
								wide: true,
								message: `<table class="table table-bordered" style="font-size:12px">${rows}</table>`,
							});
							this.load();
						},
					});
				}
			);
		});

		$(".nah-act").on("click", (e) => frappe.new_doc($(e.currentTarget).data("new")));

		$(".nah-w").on("click", (e) => {
			const w = d.my_work[+$(e.currentTarget).data("work")];
			if (!w || !w.route) return;
			if (w.route[0] === "new") frappe.new_doc(w.route[1]);
			else frappe.set_route(...w.route);
		});

		$(".nah-node").on("click", (e) => {
			const lane = d.lanes[+$(e.currentTarget).data("lane")];
			const node = lane.nodes[+$(e.currentTarget).data("node")];
			if (node && node.route) frappe.set_route(...node.route);
		});

		$(".nah-link").on("click", (e) => {
			const tile = d.tiles[+$(e.currentTarget).data("tile")];
			const link = tile.links[+$(e.currentTarget).data("link")];
			if (link.kind === "Page") frappe.set_route(link.target);
			else if (link.kind === "Report") frappe.set_route("query-report", link.target);
			else frappe.set_route("List", link.target);
		});
	}

	// ------------------------------------------------------------ styles
	inject_styles() {
		if (document.getElementById("nah-styles")) return;
		$(`<style id="nah-styles">
		.nah { padding-bottom: 48px; }

		.nah-hero { background:linear-gradient(135deg,#13293D 0%,#1B98E0 100%); color:#fff;
			border-radius:12px; padding:20px 22px; margin-bottom:20px; }
		.nah-hero-t { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }
		.nah-logo { width:44px; height:44px; flex:none;
			filter:drop-shadow(0 2px 6px rgba(0,0,0,.25)); }
		.nah-greet { font-size:22px; font-weight:600; }
		.nah-sub { font-size:13px; opacity:.9; margin-top:3px; }
		.nah-chip { background:rgba(255,255,255,.2); border-radius:20px; padding:2px 10px;
			font-size:11px; margin-left:8px; }
		.nah-date { font-size:12px; opacity:.85; }
		.nah-acts { display:flex; gap:8px; flex-wrap:wrap; margin-top:16px; }
		.nah-act { background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.25);
			color:#fff; border-radius:8px; padding:7px 12px; font-size:12px; cursor:pointer;
			display:flex; gap:6px; align-items:center; transition:.15s; }
		.nah-act:hover { background:rgba(255,255,255,.3); transform:translateY(-1px); }

		.nah-banner { background:#FEF3C7; border:1px solid #FCD34D; border-radius:8px;
			padding:11px 14px; margin-bottom:18px; font-size:13px;
			display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
		.nah-misses { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
		.nah-miss { background:rgba(0,0,0,.06); border-radius:5px; padding:2px 8px; font-size:11px; }
		.nah-miss b { color:var(--red-600); }

		.nah-sec-h { font-size:12px; font-weight:600; text-transform:uppercase;
			letter-spacing:.06em; color:var(--text-muted); margin:22px 0 10px; }
		.nah-sec-s { text-transform:none; letter-spacing:0; font-weight:400; margin-left:8px; }

		.nah-work { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:11px; }
		.nah-w { background:var(--card-bg); border:1px solid var(--border-color);
			border-left:3px solid var(--blue-500,#1B98E0); border-radius:9px;
			padding:12px 14px; cursor:pointer; transition:.15s; }
		.nah-w:hover { transform:translateY(-2px); box-shadow:0 3px 10px rgba(0,0,0,.08); }
		.nah-w.good { border-left-color:var(--green-500,#10B981); }
		.nah-w.warn { border-left-color:var(--orange-500,#F59E0B); }
		.nah-w.bad  { border-left-color:var(--red-500,#EF4444); }
		.nah-w-l { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--text-muted); }
		.nah-w-v { font-size:19px; font-weight:600; margin-top:3px; }
		.nah-w-s { font-size:11px; color:var(--text-muted); margin-top:4px; line-height:1.35; }

		.nah-flow { display:flex; flex-direction:column; gap:0; }
		.nah-lane { background:var(--card-bg); border:1px solid var(--border-color);
			border-top:3px solid var(--lc); border-radius:10px; padding:12px 14px; }
		.nah-lane-h { font-size:12px; font-weight:600; color:var(--lc);
			display:flex; gap:7px; align-items:center; margin-bottom:10px; }
		.nah-nodes { display:flex; align-items:stretch; gap:0; flex-wrap:wrap; }
		.nah-node { flex:1 1 130px; min-width:120px; border:1px solid var(--border-color);
			border-radius:8px; padding:9px 11px; cursor:pointer; background:var(--bg-color,#fff);
			transition:.15s; position:relative; }
		.nah-node:hover { border-color:var(--lc); transform:translateY(-2px);
			box-shadow:0 3px 10px rgba(0,0,0,.07); }
		.nah-node-l { font-size:12px; font-weight:500; }
		.nah-node-c { font-size:18px; font-weight:600; margin-top:3px; color:var(--text-muted);
			font-variant-numeric:tabular-nums; }
		.nah-node-c.hot { color:var(--lc); }

		.nah-arrow { flex:0 0 26px; display:flex; align-items:center; justify-content:center; }
		.nah-arrow i { display:block; width:100%; height:2px; background:var(--border-color);
			position:relative; overflow:hidden; }
		.nah-arrow i::after { content:''; position:absolute; inset:0;
			background:linear-gradient(90deg,transparent,var(--lc),transparent);
			animation:nah-slide 2.2s linear infinite; }
		@keyframes nah-slide { from{transform:translateX(-100%)} to{transform:translateX(100%)} }

		.nah-lane-link { height:18px; display:flex; justify-content:center; }
		.nah-lane-link i { width:2px; height:100%; background:var(--border-color);
			position:relative; overflow:hidden; }
		.nah-lane-link i::after { content:''; position:absolute; inset:0;
			background:linear-gradient(180deg,transparent,#1B98E0,transparent);
			animation:nah-drop 2.2s linear infinite; }
		@keyframes nah-drop { from{transform:translateY(-100%)} to{transform:translateY(100%)} }

		.nah-tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); gap:12px; }
		.nah-tile { background:var(--card-bg); border:1px solid var(--border-color);
			border-radius:10px; padding:13px 15px; transition:.15s; }
		.nah-tile:hover { box-shadow:0 3px 12px rgba(0,0,0,.07); }
		.nah-tile-h { font-size:13px; font-weight:600; display:flex; gap:8px;
			align-items:center; margin-bottom:9px; color:var(--tc); }
		.nah-tile-i { font-size:16px; }
		.nah-tile-links { display:flex; flex-direction:column; gap:2px; }
		.nah-link { font-size:12px; color:var(--text-color); padding:3px 6px; margin-left:-6px;
			border-radius:5px; cursor:pointer; text-decoration:none; }
		.nah-link:hover { background:var(--fg-hover-color,#f1f5f9); color:var(--tc); text-decoration:none; }

		.nah-none { text-align:center; padding:60px 20px; }

		@media (max-width:700px){
			.nah-arrow { display:none; }
			.nah-node { flex:1 1 45%; margin:3px 0; }
			.nah-greet { font-size:19px; }
		}
		</style>`).appendTo("head");
	}
}
