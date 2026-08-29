# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class BatchSequenceCounter(Document):
	"""Storage only. Values are allocated under a row lock by
	neoaqua.manufacturing.batch_naming.allocate_counter - never edit by hand
	unless you intend to change the next number issued."""

	pass
