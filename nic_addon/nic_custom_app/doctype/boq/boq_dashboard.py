from frappe import _


def get_data():
	return {
		"fieldname": "boq",
		"transactions": [
			{"label": _("Estimation"), "items": ["BOQ Section", "Direct Cost"]},
		],
	}
