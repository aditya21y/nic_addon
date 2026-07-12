# Copyright (c) 2026, aditya&bagas and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


class WorkAnalysis(Document):
	def validate(self):
		self.validate_analysis_code()
		self.calculate_amounts()

	def validate_analysis_code(self):
		"""A Composite analysis_code must point at a non-stock (service) Item."""
		if self.analysis_type == "Composite" and self.analysis_code:
			if frappe.db.get_value("Item", self.analysis_code, "is_stock_item"):
				frappe.throw(
					_("Analysis Code {0} must be a non-stock Item (is_stock_item = 0).").format(
						frappe.bold(self.analysis_code)
					)
				)

	def calculate_amounts(self):
		"""Compute per-component amounts and roll them up into the out_* rates.

		Item rows (those with an ``item_code``) are ``qty × rate`` — for a Simple
		analysis the qty is always 1. Percentage rows (no ``item_code``, e.g.
		"Waste 2%") are ``percentage % × subtotal of the item rows``.
		"""
		is_simple = self.analysis_type == "Simple"

		# First pass: the qty × rate subtotals are the bases the percentages
		# apply against (the net material / labor of the components).
		material_base = 0.0
		labor_base = 0.0
		for c in self.components:
			qty = 1 if is_simple else flt(c.qty)
			material_base += qty * flt(c.material_rate)
			labor_base += qty * flt(c.labor_rate)

		# Second pass: each row is qty × rate PLUS its percentage of the base.
		for c in self.components:
			qty = 1 if is_simple else flt(c.qty)
			c.amount_material = flt(qty * flt(c.material_rate) + flt(c.material_percentage) / 100 * material_base)
			c.amount_labor = flt(qty * flt(c.labor_rate) + flt(c.labor_percentage) / 100 * labor_base)

		total_material = sum(flt(c.amount_material) for c in self.components)
		total_labor = sum(flt(c.amount_labor) for c in self.components)
		self.out_material_rate = total_material
		self.out_labor_rate = total_labor
		self.out_total_rate = total_material + total_labor


@frappe.whitelist()
def get_item_price(item_code, posting_date=None):
	"""Return the buying Item Price for `item_code` that is valid on `posting_date`.

	Picks the most recent price whose `valid_from` is on or before the posting
	date (latest valid_from wins), ignoring any price whose validity window has
	already closed (`valid_upto` before the posting date). Only buying price
	lists are considered.
	"""
	if not item_code:
		return None

	posting_date = getdate(posting_date or nowdate())

	row = frappe.db.sql(
		"""
		select name, price_list, price_list_rate, supplier, valid_from
		from `tabItem Price`
		where item_code = %(item_code)s
			and buying = 1
			and (valid_from is null or valid_from <= %(date)s)
			and (valid_upto is null or valid_upto = '' or valid_upto >= %(date)s)
		order by valid_from desc, modified desc
		limit 1
		""",
		{"item_code": item_code, "date": posting_date},
		as_dict=True,
	)

	if not row:
		return None

	return {
		"item_price": row[0].name,
		"price_list_rate": row[0].price_list_rate,
		"price_list": row[0].price_list,
		"supplier": row[0].supplier,
		"valid_from": row[0].valid_from,
	}
