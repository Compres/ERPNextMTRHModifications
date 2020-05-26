# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

# ERPNext - web based ERP (http://erpnext.com)
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, json
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import get_url, cint
from frappe.utils.background_jobs import enqueue
from frappe import msgprint
from frappe.model.document import Document
import datetime
from frappe.utils import cint, flt, cstr, now
from datetime import date, datetime

class TQE(Document):
	pass
@frappe.whitelist()
def rfq_send_emails_suppliers(rfqno):
	userlist = frappe.db.get_list("Request For Quotation Adhoc Committee",
			filters={
				"parent": rfqno,				
			},
			fields=["user_mail","employee_name","user_password"],
			ignore_permissions = True,
			as_list=False
		)			
	lis_users =[]
	send_email_to_adhoc(userlist,rfqno)
	frappe.response["usermails"] =lis_users

@frappe.whitelist()
def send_email_to_adhoc(users_data,rfqno):
	#common_args = get_common_email_args(doc)
	message = "here is the password for adhoc"
	#common_args.pop('message', None)
	for d in users_data:
		email_args = {
			'recipients': d.user_mail,
			'args': {
				#'actions': list(deduplicate_actions(d.get('possible_actions'))),
				'message': message
			},
			'reference_name': rfqno,
			'reference_doctype': rfqno
		}
		#email_args.update(common_args)
		enqueue(method=frappe.sendmail, queue='short', **email_args)
@frappe.whitelist()
def Generate_Purchase_Receipt_Draft(doc):
	doc1 = json.loads(doc)
	purchase_order_name = doc1.get('name')
	items = doc1.get('items')	
	supplier_name= frappe.db.get_value('Purchase Order', purchase_order_name, 'supplier')	
	#frappe.msgprint(balance_to_supply)
	#frappe.throw(items)
	
	"""
	itemqtylist = frappe.db.get_list("Purchase Order Item",
			filters={
				"parent": purchase_order_name,				
			},
			fields=["qty"],
			ignore_permissions = True,
			as_list=False
			)
	#frappe.throw(itemqtylist)			
	for totalqty in itemqtylist:		
		itemq =totalqty.qty
	frappe.msgprint("Item set as attended to: "+str(itemq))		
	if(itemq<40):
		#frappe.msgprint("Item set as attended to: "+itemq)			
	frappe.throw(totalqty.qty)	
	"""	
	itemlistarray=[]
	row={}
	items_payload = json.dumps(items)
	payload_to_use = json.loads(items_payload)
	today = str(date.today())
	for item in payload_to_use:		
		row["item_code"]=item.get("item_code")	
		row["item_name"]=item.get("item_name")		
		row["description"]=item.get("item_name")		
		row["qty"]=item.get("tosupply")		
		row["conversion_factor"]=1
		row["schedule_date"]= today 
		row["rate"] = item.get("rate")		
		row["amount"] = item.get("amount")	
		row["purchase_order"]=purchase_order_name		
		row["stock_uom"]=item.get("stock_uom")
		row["uom"] =item.get("uom")
		row["brand"]=item.get("brand")	
		row["net_amount"]=item.get("amount")
		row["base_rate"] = item.get("rate") 
		row["base_amount"] = item.get("amount")
		row["department"] = item.get("department")
		row["expense_account"] = item.get("expense_account")
		row["material_request"] = item.get("material_request")
		row["rejected_warehouse"] = item.get("warehouse")

		
		#delivery_note = item.get("deliverynote")					
		itemlistarray.append(row)			
	
	for item_in in itemlistarray:				
		balance_to_supply=getquantitybalance(purchase_order_name,item_in.get("item_code"))
		itemqtysupplied=int(item_in.get("qty"))
		balance_qty=int(balance_to_supply)
		#frappe.throw(balance_qty)
		#frappe.msgprint(str(item_in.get("qty")))
		if itemqtysupplied>balance_qty:
			frappe.throw("You have Exceeded the quantity required to Supply.Kindly Check")
		else:
			#frappe.msgprint("wedddddddddd")
			#frappe.throw(balance_to_supply)
		
			doc = frappe.new_doc('Purchase Receipt')
			doc.update(
					{	
						"naming_series":"MAT-PRE-.YYYY.-",
						"supplier":supplier_name,	
						"supplier_name":supplier_name,
						"posting_date":date.today(),
						"posting_time":datetime.now(),
						"company":frappe.defaults.get_user_default("company"),		
						"supplier_delivery_note":908754,
						"currency":frappe.defaults.get_user_default("currency"),
						"conversion_rate":"1",
						"items":itemlistarray														
					}
			)
			doc.insert(ignore_permissions = True)
			frappe.response['type'] = 'redirect'	
			frappe.response.location = '/Supplier-Delivery-Note/Supplier-Delivery-Note/'

		
@frappe.whitelist()
def make_purchase_invoice_from_portal(purchase_order_name):		
	#doc = frappe.get_doc('Purchase Order Item', purchase_order_name) 
	#itemcode=doc.item_codess
	
	itemslist = frappe.db.get_list("Purchase Order Item",
			filters={
				"parent": purchase_order_name,				
			},
			fields=["item_code","item_name","qty"],
			ignore_permissions = True,
			as_list=False
		)
	itemlistarray=[]	
	for item in itemslist:
		itemlistarray.append(item.item_code)	
	frappe.throw(itemslist)
	frappe.response['type'] = 'redirect'	
	frappe.response.location = '/Supplier-Delivery-Note/Supplier-Delivery-Note/'	
	#frappe.response['delivey']=	deliverynotelist 

@frappe.whitelist()
def send_adhoc_members_emails(doc, state):	#method to send emails to adhoc members
	docname = doc.get('name')	
	adhocmembers =frappe.db.get_list("Request For Quotation Adhoc Committee", #get the list
		filters={
			 "parent":docname
			 } ,
			fields=["employee_name","user_mail","user_password"],
			ignore_permissions = True,
			as_list=False
		)
	adhoc_list =[]	
	for usermail in adhocmembers: #loop and get the mail array and create the arguments
		adhoc_list.append(usermail.user_mail)	
		send_notifications(adhoc_list,"Your password for Tender/Quotation Evaluation is:"+usermail.user_password,"Tender/Quotation Evaluation Credentials for::"+docname,doc.get("doctype"),docname)	
	frappe.response["mem"]=adhoc_list	

def send_notifications(adhoc_list, message,subject,doctype,docname):
	#template_args = get_common_email_args(None)
	email_args = {
				"recipients": adhoc_list,
				"message": _(message),
				"subject": subject,
				#"attachments": [frappe.attach_print(self.doctype, self.name, file_name=self.name)],
				"reference_doctype": doctype,
				"reference_name": docname,
				}	
	enqueue(method=frappe.sendmail, queue='short', timeout=300, **email_args)

def getquantitybalance(purchase_order_name,itemcode):
	total_qty=frappe.db.sql("""SELECT coalesce(sum(qty),0) FROM `tabPurchase Order Item` WHERE parent=%s and item_code=%s""",(purchase_order_name,itemcode))
	total_amount_supplied=frappe.db.sql("""SELECT coalesce(sum(qty),0) FROM `tabPurchase Receipt Item` where purchase_order=%s and item_code=%s""",(purchase_order_name,itemcode))
	quantity_balance = (total_qty [0][0])-(total_amount_supplied[0][0])	
	#return flt(total_qty[0][0]) if total_qty else 0.
	#return total_amount_supplied if total_amount_supplied else 0
	return quantity_balance if quantity_balance else 0