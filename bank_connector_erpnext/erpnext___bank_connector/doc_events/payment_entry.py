import frappe
import json
import uuid, requests
import random
from erpnext.controllers.queries import get_fields
from frappe.desk.reportview import get_filters_cond, get_match_cond

@frappe.whitelist()
def make_payment_order(source_name, target_doc=None):
	from frappe.model.mapper import get_mapped_doc

	def set_missing_values(source, target):
		target.payment_order_type = "Payment Entry"
		account = ""
		party_bank_account =""
		if not source.party_bank_account:
			party_bank_account = frappe.db.get_value("Bank Account",{"party_type":source.party_type,"party":source.party}) or ""
		if source.paid_to:
			account = source.paid_to
		target.append(
			"references",
			{
				"reference_doctype": "Payment Entry",
				"reference_name": source.name,
				"amount": source.paid_amount,
				"party_type": source.party_type,
				"party": source.party,
				"mode_of_payment": source.mode_of_payment,
				"bank_account": source.party_bank_account,
				"account": account,
				"cost_center": source.cost_center,
				"project": source.project,
				"tax_withholding_category": source.tax_withholding_category,
			},
		)
		target.status = "Pending"

	doclist = get_mapped_doc(
		"Payment Entry",
		source_name,
		{
			"Payment Entry": {
				"doctype": "Payment Order",
			}
		},
		target_doc,
		set_missing_values,
	)

	return doclist

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def fetch_unprocessed_payment_entries(doctype, txt, searchfield, start, page_len, filters, as_dict):
	doctype = "Payment Entry"
	condition = ""
	fields = get_fields(doctype, ["name", "party", "paid_amount"])
	por = frappe.db.sql('''select `tabPayment Order Reference`.reference_name as name from `tabPayment Entry` 
					 right join `tabPayment Order Reference` on `tabPayment Entry`.name = `tabPayment Order Reference`.reference_name 
					 where `tabPayment Entry`.docstatus = 1 and `tabPayment Order Reference`.reference_doctype = "Payment Entry" ''',as_dict=1)
	if len(por) and "name" in por[0]:
		condition += '''and `tabPayment Entry`.name not in ({0}) '''.format(", ".join(["'{0}'".format(f["name"]) for f in por]))
	sql = frappe.db.sql('''select {0} from `tabPayment Entry` left join `tabPayment Order Summary` 
					 on `tabPayment Entry`.name = `tabPayment Order Summary`.payment_entry 
					 where `tabPayment Order Summary`.name is null {2} and  
					 `tabPayment Entry`.docstatus = 1 {1} and `tabPayment Entry`.{3} like "%{4}%" limit {5} offset {6}'''.format(", ".join(["`tabPayment Entry`.{0}".format(f) for f in fields]),get_filters_cond(doctype,filters,[]),condition,searchfield,txt,page_len,start),as_dict=1)
	return sql
