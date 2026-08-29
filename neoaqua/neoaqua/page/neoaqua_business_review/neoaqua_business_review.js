// Copyright (c) 2026, Neotec Integrated Solutions
frappe.pages["neoaqua-business-review"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper, title: __("Business Review"), single_column: true,
	});
	new BusinessReview(page);
};

class BusinessReview {
	constructor(page) { this.page = page; this.setup(); }

	setup() {
		const today = frappe.datetime.get_today();
		const first = frappe.datetime.add_months(frappe.datetime.month_start(), -1);
		this.f = {};
		const add = (s) => (this.f[s.fieldname] = this.page.add_field(s));
		add({ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		      default: frappe.defaults.get_user_default("Company"), change: () => this.load() });
		add({ fieldname: "from_date", label: __("From"), fieldtype: "Date",
		      default: first, change: () => this.load() });
		add({ fieldname: "to_date", label: __("To"), fieldtype: "Date",
		      default: frappe.datetime.add_days(frappe.datetime.month_start(), -1),
		      change: () => this.load() });

		this.page.set_primary_action(__("Email to Management"), () => this.email(), "mail");
		this.page.add_menu_item(__("Print"), () => this.print());
		this.page.add_menu_item(__("Download PDF"), () => this.download("pdf"));
		this.page.add_menu_item(__("Download Excel"), () => this.download("xlsx"));
		this.page.add_menu_item(__("Refresh"), () => this.load());

		this.page.main.html(`<div id="brv-host" style="background:#fff;border:1px solid var(--border-color);
			border-radius:10px;padding:26px 30px"></div>`);
		this.load();
	}

	args() {
		return {
			company: this.f.company.get_value(),
			from_date: this.f.from_date.get_value(),
			to_date: this.f.to_date.get_value(),
		};
	}

	load() {
		frappe.call({
			method: "neoaqua.api.business_review.get_html",
			args: this.args(),
			freeze: true, freeze_message: __("Assembling the review..."),
			callback: (r) => {
				this.data = r.message || {};
				$("#brv-host").html(this.data.html || "");
			},
		});
	}

	print() {
		const w = window.open("", "_blank");
		w.document.write(`<html><head><title>${__("Business Review")}</title></head>
			<body style="margin:24px">${this.data.html}</body></html>`);
		w.document.close();
		setTimeout(() => w.print(), 400);
	}

	download(kind) {
		const a = this.args();
		const method = kind === "pdf"
			? "neoaqua.api.business_review.download_pdf"
			: "neoaqua.api.business_review.download_xlsx";
		open_url_post("/api/method/" + method, a);
	}

	email() {
		const pack = this.data.pack || {};
		const d = new frappe.ui.Dialog({
			title: __("Email the Business Review"),
			fields: [
				{ fieldname: "recipients", fieldtype: "Data", reqd: 1, label: __("To"),
				  description: __("Comma separated") },
				{ fieldname: "subject", fieldtype: "Data", label: __("Subject"),
				  default: __("{0} — Business Review {1} to {2}",
				    [pack.brand || pack.company, pack.from_date, pack.to_date]) },
				{ fieldname: "message", fieldtype: "Small Text", label: __("Covering note") },
				{ fieldname: "attach_pdf", fieldtype: "Check", label: __("Attach PDF"), default: 1 },
				{ fieldtype: "HTML", options:
				  `<p class="text-muted small">${__("The review is sent in the body of the email as well, so it can be read on a phone without opening the attachment.")}</p>` },
			],
			primary_action_label: __("Send"),
			primary_action: (v) => {
				frappe.call({
					method: "neoaqua.api.business_review.send_email",
					args: { ...this.args(), ...v },
					freeze: true, freeze_message: __("Sending..."),
					callback: (r) => {
						d.hide();
						frappe.show_alert({ message: (r.message || {}).message, indicator: "green" });
					},
				});
			},
		});
		d.show();
	}
}
