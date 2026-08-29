# Copyright (c) 2026, Neotec Integrated Solutions
"""Install the NeoAqua custom fields on standard doctypes."""

from neoaqua.setup import custom_fields


def execute():
	custom_fields.install()
