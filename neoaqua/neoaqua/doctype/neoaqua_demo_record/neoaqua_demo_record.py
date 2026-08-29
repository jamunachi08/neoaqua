# Copyright (c) 2026, Neotec Integrated Solutions and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class NeoAquaDemoRecord(Document):
	"""Append-only log of documents created by the demo generator.

	The `sequence` field is what makes cleanup safe: dependents are always
	created after their dependencies, so walking the log in reverse sequence
	is a valid topological order for deletion.
	"""

	pass
