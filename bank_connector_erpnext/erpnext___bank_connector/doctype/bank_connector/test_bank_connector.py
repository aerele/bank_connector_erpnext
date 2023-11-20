# Copyright (c) 2023, Aerele Technologies Private Limited and Contributors
# See license.txt

import frappe
import json, requests
from frappe.tests.utils import FrappeTestCase


class TestBankConnector(FrappeTestCase):
	pass

@frappe.whitelist()
def make_payment(doc):
	if isinstance(doc, str):
		doc = json.loads(doc)
	
	doc = frappe._dict(doc)
	UAT_CONSENT_ID = ""
	UAT_ACC = ""
	URL = "https://uatskyway.yesbank.in/app/uat/api-banking/domestic-payments"
	payload = json.dumps(
		{
			"Data": {
				"ConsentId": UAT_CONSENT_ID,
				"Initiation": {
					"InstructionIdentification": doc.name,
					"EndToEndIdentification": "",
					"InstructedAmount": {
						"Amount": doc.amount,
						"Currency": "INR"
					},
					"DebtorAccount": {
						"Identification": UAT_ACC,
						"SecondaryIdentification": UAT_CONSENT_ID
					},
					"CreditorAccount": {
						"SchemeName": doc.branch_code,
						"Identification": doc.account_number,
						"Name": doc.party,
						"Unstructured": {
							"ContactInformation": {
								"EmailAddress": "test@aerele.in",
								"MobileNumber": "7790844832"
							}
						}
					},
					"RemittanceInformation": {
						"Reference": doc.name,
						"Unstructured": {
							"CreditorReferenceInformation": "RemeToBeneInfo"
						}
					},
					"ClearingSystemIdentification": doc.mode_of_transfer
				}
			},
			"Risk": {
				"DeliveryAddress": {
					"AddressLine": [
						"Flat 7",
						"Acacia Lodge"
					],
					"StreetName": "Acacia Avenue",
					"BuildingNumber": "27",
					"PostCode": "600524",
					"TownName": "MUM",
					"CountySubDivision": [
						"MH"
					],
					"Country": "IN"
				}
			}
		}
	)

	HEADERS = {
		'X-IBM-Client-Id': '186e62a4-cd3e-4a86-ba02-9ceac52ee720',
		'X-IBM-Client-Secret': 'G3nM7wF5aI1nR8wC3nJ0lQ3xC2yQ8gA4xV1yK1hV2eC4mS2aP0',
		'Authorization': 'Basic dGVzdHVzZXI6VGlFc2JudHBAMTNOMjI=',
		'Content-Type': 'application/json'
	}

	bank_request_log_doc = frappe.new_doc("Bank Request Log")
	bank_request_log_doc.payload = payload
	bank_request_log_doc.request_id = doc.name

	response = requests.request("POST", URL, headers=HEADERS, data=payload, cert=("/home/ubuntu/yesbank_testing/cert.pem", "/home/ubuntu/yesbank_testing/privatekey.pem"))
	bank_request_log_doc.response = response.text
	bank_request_log_doc.insert(ignore_permissions=True)

	payment_status = "Failed"
	if response.status_code == 200:
		response_data = json.loads(response.text)
		if "Data" in response_data and response_data["Data"]:
			if "Status" in response_data["Data"] and response_data["Data"]["Status"]:
				response_status = response_data["Data"]["Status"]
				if response_status == "Duplicate":
					payment_status = "Failed"
				elif response_status == "Received":
					payment_status = "Initiated"
	return {"payment_status": payment_status}


def get_payment_status(doc):
	URL = "https://uatskyway.yesbank.in/app/uat/api-banking/payment-details"
	if isinstance(doc, str):
		doc = json.loads(doc)
	
	doc = frappe._dict(doc)
	UAT_CONSENT_ID = "453733"
	UAT_ACC = "000190600017042"
	payload = json.dumps({
			"Data": {
				"InstrId": doc.request_id,
				"ConsentId": UAT_CONSENT_ID,
				"SecondaryIdentification": UAT_ACC
			}
		}
	)
	HEADERS = {
		'X-IBM-Client-Id': '186e62a4-cd3e-4a86-ba02-9ceac52ee720',
		'X-IBM-Client-Secret': 'G3nM7wF5aI1nR8wC3nJ0lQ3xC2yQ8gA4xV1yK1hV2eC4mS2aP0',
		'Authorization': 'Basic dGVzdHVzZXI6VGlFc2JudHBAMTNOMjI=',
		'Content-Type': 'application/json'
	}

	response = requests.request("POST", URL, headers=HEADERS, data=payload, cert=("/home/ubuntu/yesbank_testing/cert.pem", "/home/ubuntu/yesbank_testing/privatekey.pem"))

	reference_number = None
	payment_status = None
	if response.status_code == 200:
		response_data = json.loads(response.text)
		print("response","\n\n\n",response_data)
		if "Data" in response_data and response_data["Data"]:
			if "Initiation" in response_data["Data"] and response_data["Data"]["Initiation"]:
				if "EndToEndIdentification" in response_data["Data"]["Initiation"] and response_data["Data"]["Initiation"]["EndToEndIdentification"]:
					reference_number = response_data["Data"]["Initiation"]["EndToEndIdentification"]
			if "Status" in response_data["Data"] and response_data["Data"]["Status"]:
				response_status = response_data["Data"]["Status"]
				if response_status in ["SettlementInProcess", "Pending"]:
					payment_status = "Initiated"
				elif response_status == "SettlementCompleted":
					payment_status = "Processed"
				elif response_status in ["SettlementReversed", "FAILED"]:
					payment_status = "Failed"
				
	return {"payment_status": payment_status, "reference_number": reference_number}



