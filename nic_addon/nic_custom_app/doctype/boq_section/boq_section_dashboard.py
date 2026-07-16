from frappe import _


def get_data():
	return {
		"fieldname": "boq_section",
		"internal_links": {
			"Work Analysis": ["items", "source_type"],
			"Item": ["items", "item_code"],
		},
		"transactions": [
			{"label": _("Analysis"), "items": ["Work Analysis"]},
			{"label": _("Items"), "items": ["Item"]},
		],
	}
