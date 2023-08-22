import frappe

def after_install():
	allow_payment_request_creation()
	disable_reqd_for_reference_in_payment_order()

def allow_payment_request_creation():
	frappe.db.set_value("DocType", "Payment Request", "in_create", 0)
	frappe.db.set_value("DocType", "Payment Request", "track_changes", 1)

def disable_reqd_for_reference_in_payment_order():
	po_type = frappe.db.get_value("DocField", {"parent": "Payment Order Reference", "fieldname": "reference_doctype"})
	po_doc = frappe.db.get_value("DocField", {"parent": "Payment Order Reference", "fieldname": "reference_name"})
	po_amount = frappe.db.get_value("DocField", {"parent": "Payment Order Reference", "fieldname": "amount"})
	frappe.db.set_value("DocField", po_type, "reqd", 0)
	frappe.db.set_value("DocField", po_doc, "reqd", 0)
	frappe.db.set_value("DocField", po_amount, "reqd", 0)
	frappe.db.set_value("DocField", po_amount, "read_only", 0)

	po_doctype = frappe.db.get_value("DocField", {"parent": "Payment Order", "fieldname": "payment_order_type"})
	frappe.db.set_value("DocField", po_doctype, "options", "\nPayment Request\nPayment Entry\nPurchase Invoice")