# Copyright (c) 2026, Neotec Integrated Solutions
"""Jinja helpers exposed to print formats."""

import frappe
from frappe.utils import flt, formatdate

AR_MONTHS = [
	"يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
	"يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]


def fmt_sar(value, decimals=2):
	return f"{flt(value):,.{decimals}f} SAR"


def arabic_date(value):
	if not value:
		return ""
	d = frappe.utils.getdate(value)
	return f"{d.day} {AR_MONTHS[d.month - 1]} {d.year}"
