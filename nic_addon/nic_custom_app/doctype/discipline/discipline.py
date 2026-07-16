# Copyright (c) 2026, aditya&bagas and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Discipline(Document):
	def validate(self):
		if self.item and frappe.db.get_value("Item", self.item, "is_stock_item"):
			frappe.throw(
				_("Item {0} must be a non-stock (service) Item to be used as a Sales Order line.").format(
					frappe.bold(self.item)
				)
			)
