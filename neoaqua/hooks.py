from . import __version__ as app_version  # noqa

app_name = "neoaqua"
app_title = "NeoAqua"
app_publisher = "Neotec Integrated Solutions"
app_description = "Bottled Water Plant, Van Sales & Distribution Suite for ERPNext (KSA)"
app_email = "info@neotec.sa"
app_license = "Commercial"
app_logo_url = "/assets/neoaqua/images/neoaqua-logo.svg"
required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------- assets
app_include_js = "neoaqua.bundle.js"
app_include_css = "neoaqua.bundle.css"

doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js",
    "Work Order": "public/js/work_order.js",
    "Stock Entry": "public/js/stock_entry.js",
    "Material Request": "public/js/material_request.js",
    "Batch": "public/js/batch.js",
}

# ---------------------------------------------------------------- install
after_install = "neoaqua.setup.install.after_install"
after_migrate = "neoaqua.setup.install.after_migrate"
before_uninstall = "neoaqua.setup.install.before_uninstall"

# ---------------------------------------------------------------- fixtures
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["module", "=", "NeoAqua"]],
    },
    {
        "dt": "Property Setter",
        "filters": [["module", "=", "NeoAqua"]],
    },
    {
        "dt": "Role",
        "filters": [["name", "in", [
            "NeoAqua Manager", "Van Salesman", "Van Supervisor",
            "Plant Operator", "QC Inspector", "Cashier - Water",
        ]]],
    },
]

# ---------------------------------------------------------------- doc events
doc_events = {
    "Sales Invoice": {
        "validate": [
            "neoaqua.van_sales.invoice_hooks.validate_van_invoice",
            "neoaqua.van_sales.invoice_hooks.apply_container_deposit",
        ],
        "on_submit": "neoaqua.van_sales.invoice_hooks.on_submit_van_invoice",
        "on_cancel": "neoaqua.van_sales.invoice_hooks.on_cancel_van_invoice",
    },
    "POS Invoice": {
        "validate": "neoaqua.van_sales.invoice_hooks.validate_van_invoice",
        "on_submit": "neoaqua.van_sales.invoice_hooks.on_submit_van_invoice",
    },
    "Payment Entry": {
        "on_submit": "neoaqua.van_sales.collection_hooks.tag_trip_collection",
    },
    "Stock Entry": {
        "validate": "neoaqua.manufacturing.batch_hooks.apply_batch_to_stock_entry",
        "before_submit": "neoaqua.manufacturing.qc_hooks.block_fg_transfer_without_qc",
    },
    "Work Order": {
        "validate": "neoaqua.manufacturing.wo_hooks.set_production_line",
        "on_submit": [
            "neoaqua.manufacturing.batch_hooks.reserve_batch_for_work_order",
            "neoaqua.manufacturing.wo_hooks.on_work_order_submit",
        ],
        "on_cancel": "neoaqua.manufacturing.batch_hooks.release_reserved_batch",
    },
    "Batch": {
        "autoname": "neoaqua.manufacturing.batch_hooks.batch_autoname",
        "validate": "neoaqua.manufacturing.batch_hooks.batch_validate",
    },
    "Water Quality Check": {
        "on_submit": "neoaqua.manufacturing.batch_hooks.sync_qc_status_to_batch",
    },
    "Purchase Order": {
        "validate": "neoaqua.procurement.p2p_hooks.validate_supplier_compliance",
    },
    "Purchase Receipt": {
        "validate": "neoaqua.procurement.p2p_hooks.validate_coa_on_receipt",
    },
}

# ---------------------------------------------------------------- scheduler
scheduler_events = {
    "cron": {
        # every 15 min: flag salesmen who have not checked in on planned stops
        "*/15 * * * *": ["neoaqua.van_sales.geofence.flag_missed_visits"],
    },
    "monthly": [
        "neoaqua.api.business_review.send_monthly_review",
    ],
    "daily": [
        "neoaqua.van_sales.day_close.notify_pending_day_close",
        "neoaqua.manufacturing.expiry.flag_near_expiry_batches",
        "neoaqua.van_sales.containers.rebuild_container_balances",
    ],
    "hourly": [
        "neoaqua.manufacturing.wo_hooks.refresh_production_dashboard_cache",
    ],
}

# ---------------------------------------------------------------- permissions
permission_query_conditions = {
    "Van Trip": "neoaqua.van_sales.permissions.van_trip_query",
    "Salesman Day Close": "neoaqua.van_sales.permissions.day_close_query",
    "Salesman Check In": "neoaqua.van_sales.permissions.check_in_query",
}

has_permission = {
    "Van Trip": "neoaqua.van_sales.permissions.van_trip_has_permission",
}

# ---------------------------------------------------------------- dashboards
override_doctype_dashboards = {
    "Customer": "neoaqua.van_sales.containers.customer_dashboard",
}

# ---------------------------------------------------------------- portal
website_route_rules = [
    {"from_route": "/van-sales/<path:app_path>", "to_route": "van-sales"},
]

# ---------------------------------------------------------------- jinja
jinja = {
    "methods": [
        "neoaqua.utils.formatting.fmt_sar",
        "neoaqua.utils.formatting.arabic_date",
    ]
}
