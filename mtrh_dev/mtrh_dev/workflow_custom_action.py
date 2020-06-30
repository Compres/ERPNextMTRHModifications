# -*- coding: utf-8 -*-
# Copyright (c) 2020, MTRH and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe , json
from frappe import msgprint
from frappe.model.document import Document
from frappe.utils.background_jobs import enqueue
from frappe.utils import get_url, get_datetime
from frappe.desk.form.utils import get_pdf_link
from frappe.utils.verified_command import get_signed_params, verify_request
from frappe import _
from frappe.model.workflow import apply_workflow, get_workflow_name, \
	has_approval_access, get_workflow_state_field, send_email_alert, get_workflow_field_value
from frappe.desk.notifications import clear_doctype_notifications
from frappe.model.mapper import get_mapped_doc
from frappe.utils.user import get_users_with_role
import datetime
from datetime import date
from erpnext.stock.get_item_details import get_serial_no
from frappe.utils import nowdate, getdate, add_days, add_years, cstr
import copy
class WorkFlowCustomAction(Document):
	pass
#https://discuss.erpnext.com/t/popup-message-using-frappe-publish-realtime/37286/2
def process_workflow_custom_actions(doc, state):
	workflow = get_workflow_name(doc.get('doctype'))
	current_state = doc.status
	docname = doc.name
	full_user_name = frappe.db.get_value("User",frappe.session.user,"full_name")
	#frappe.msgprint("Current state "+str(current_state))
	#if current_state== "Cancelled" or current_state =="Terminated" or current_state =="Rejected":
	#frappe.publish_realtime(event='eval_js', message='alert("{0}")', user=frappe.session.user)
	# msgprint with server and client side action
	frappe.msgprint(msg='You '+current_state+" document "+docname+" please click the appropriate reason. If you need to add a comment please scroll to the bottom of this document and tag specific users",
		title='Document '+docname+' '+current_state,
		#raise_exception=FileNotFoundError
		primary_action={
			'label': _('Alert stakeholders for action'),
			'server_action': 'dotted.path.to.method',
			'args': {"comment_type":"Comment","comment_email":full_user_name, "reference_doctype":"Material Request", "reference_name":docname, content:""} })
@frappe.whitelist()
#Called by the frappe.prompt procedure in process_workflow_custom_actions method
def apply_custom_action(comment_type,comment_email,reference_doctype,reference_name):
	doc = frappe.new_doc('Comment')
	doc.comment_type = comment_type
	doc.comment_email = comment_email
	doc.reference_doctype = reference_doctype
	doc.reference_name = reference_name
	doc.insert()
	frappe.response["message"]=doc
def update_material_request_item_status(doc, state):
	doctype = doc.get('doctype')
	items = doc.items
	if(doctype=="Request for Quotation"):
		material_requests = doc.material_requests
		mreq_arr =[]
		items_arrs =[]
		for mr in material_requests:
			mreq_arr.append(mr.material_request)
		for item in items:
			items_arrs.append(item.item_code)
		docnames = frappe.db.get_list('Material Request Item',
			filters={
				'parent': ["IN", mreq_arr], 
				'item_code': ["IN", items_arrs] 
			},
			fields=['name'],
			#as_list=True
		)
		for cdname in docnames:
			#frappe.msgprint("Item set as attended to: "+str(cdname.name))
			frappe.db.set_value('Material Request Item', cdname.name, 'attended_to', "1")
		for mr in material_requests:	
			count_attended_to = frappe.db.sql("""SELECT count(attended_to) as attended_count FROM `tabMaterial Request Item` WHERE parent = %s AND attended_to =1 """,(mr.material_request), as_dict=1)
			count_all_items = frappe.db.sql("""SELECT count(*) as all_count FROM `tabMaterial Request Item` WHERE parent = %s""",(mr.material_request), as_dict=1)
			per_attended_to = float(count_attended_to[0].attended_count) * 100/ float(count_all_items[0].all_count)
			frappe.db.set_value('Material Request', mr.material_request, 'per_attended', float(per_attended_to))
		
	else:
		count_attended_to =0
		material_request =""
		for item in items:
			material_request = item.material_request
			item_code = item.item_code
			docname = frappe.get_value("Material Request Item", {"item_code": item_code, "parent":material_request},"name")
			frappe.db.set_value('Material Request Item', docname, 'attended_to', "1")
			count_attended_to = count_attended_to + 1
	
		count_all_items = frappe.db.sql("""SELECT count(*) as all_count FROM `tabMaterial Request Item` WHERE parent = %s""",(material_request), as_dict=1)
		per_attended_to = float(count_attended_to) * 100/ float(count_all_items[0].all_count)
		frappe.db.set_value('Material Request', material_request, 'per_attended', float(per_attended_to))
@frappe.whitelist()		
def auto_generate_purchase_order_by_material_request(doc,state):	
	doc = json.loads(doc)
	doc = frappe._dict(doc)
	frappe.msgprint("Processing Doc.."+doc.get("name"))
	#ONLY IF THE TYPE OF MATERIAL REQUEST IS OF PURCHASE TYPE.
	material_request_number  = doc.get("name")
	if doc.get("material_request_type") == "Purchase":
		material_request_document = doc
		
		items = doc.get("items")
		#We want to get the list of awarded items
		awarded_item_list = []
		for item in items:
			unawarded = frappe.db.exists({
					"doctype":"Item Default",
					"parent": item.get("item_code"),
					"default_supplier": "" 
				})
			#Apparently you cannot use an array of arguments such as default_supplier:["!=",""]in this frappe.db.exists 
			# #so I had to reverse the exclusion criteria to determin if item is unawarded, 
			# #if not, then it (obviously) is awarded
			# mind = blown :)
			if not unawarded:
				awarded_item_list.append(item.item_code)
		#If we have no empty array of awarded items 
		if awarded_item_list:
			#Let us now get suppliers who can supply these items and make respective orders for each
			supplier_list = frappe.get_list('Item Default',
											filters={
												'parent': ["IN", awarded_item_list]
											},
											fields=['default_supplier'],
											order_by='creation desc',
											as_list=False
										)
			for supplier in supplier_list:
				#Work begins here, but first let us know what items out of our awarded they can supply
				supplier_items = frappe.get_list('Item Default',
											filters={
												'parent': ["IN", awarded_item_list],
												'default_supplier': supplier.default_supplier
											},
											fields=['parent'],
											order_by='creation desc',
											as_list=False
										)
				#We have the supplier, now let us begin creating our document.
				actual_name = supplier.default_supplier
				purchase_order_items =[]
				row ={}
				# Creating rows of JSON objects representing a typical Purchase Order Item row  we need to add to the items array
				for supplier_item in supplier_items:
					item = supplier_item.parent
					row["item_code"]=supplier_item.parent
					item_dict = frappe.db.get_value('Material Request Item', {"parent":material_request_number,"item_code":supplier_item.parent}, ["item_code",  "item_name",  "description",  "item_group","brand","qty","uom", "conversion_factor", "stock_uom", "warehouse", "schedule_date", "expense_account","department"], as_dict=1)
					qty = item_dict.qty
					default_pricelist = frappe.db.get_value('Item Default', {'parent': item}, 'default_price_list')
					rate = frappe.db.get_value('Item Price',  {'item_code': item,'price_list': default_pricelist}, 'price_list_rate')
					amount = float(qty) * float(rate)
					row["item_name"]=item_dict.item_name
					row["description"]=item_dict.item_name
					row["rate"] = rate
					row["warehouse"] = item_dict.warehouse
					row["schedule_date"] = item_dict.schedule_date
					#Rate we have to get the current rate
					row["qty"]= item_dict.qty
					row["stock_uom"]=item_dict.stock_uom
					row["uom"] =item_dict.stock_uom
					row["brand"]=item_dict.brand
					row["conversion_factor"]=item_dict.conversion_factor #To be revised: what if a supplier packaging changes from what we have?
					row["material_request"] = material_request_number
					row["amount"] = amount #calculated
					row["net_amount"]=amount
					row["base_rate"] = rate 
					row["base_amount"] = amount
					row["expense_account"] = item_dict.expense_account
					row["department"] = item_dict.department
					#Let's add this row to the items array
					purchase_order_items.append(row.copy())
				#exit loop when your'e done, execute the order below and start all over for the next supplier
				doc = frappe.new_doc('Purchase Order')
				doc.update(
					{
						"supplier_name":actual_name,
						"conversion_rate":1,
						"currency":frappe.defaults.get_user_default("currency"),
						"supplier": actual_name,
						"supplier_test":actual_name,
						"company": frappe.defaults.get_user_default("company"),
						"naming_series": "PUR-ORD-.YYYY.-",
						"transaction_date" : date.today(),
						#"schedule_date" : add_days(nowdate(), 10),
						"items":purchase_order_items
					}
				)
				doc.insert()
			#Mark these items unattended finally
	
			#update_material_request_item_status(material_request_document, "state")
			#============================================================================
			#MATERIAL REQUEST FOR ISSUE AND TRANSFERS
	elif doc.get("material_request_type") in ["Material Issue","Material Transfer"]:
		frappe.msgprint("Forwarding S11 to the Stock Controller..")
		if doc.get("material_request_type") == "Material Transfer":
			to_warehouse = doc.get("set_warehouse")
			from_warehouse = doc.get("set_from_warehouse")
		else:
			to_warehouse = None
			from_warehouse = doc.get("set_warehouse")
		stock_entry_items  = doc.get("items")
		stock_entry_doc = frappe.new_doc('Stock Entry')
		updated_dict =[]
		updated_json={}
		attended_to_arr =[]
		frappe.response["status"] = "Creating a stock entry"
		for item in stock_entry_items:
			if item.get("attended_to") != "1":
				updated_json["item_code"]=item.get("item_code")
				updated_json["item_name"]=item.get("item_name")
				updated_json["department"]=item.get("deparment")
				updated_json["qty"]=item.get("qty")
				updated_json["material_request_qty"]=item.get("qty")
				updated_json["t_warehouse"]=to_warehouse
				updated_json["s_warehouse"]=from_warehouse
				transfer_qty = item.get("qty") * item.get("conversion_factor")
				updated_json["transfer_qty"]= transfer_qty
				updated_json["material_request"]= material_request_number
				updated_json["material_request_item"]=item.get("name")
				updated_json["basic_rate"]= item.get("rate")
				updated_json["valuation_rate"]=item.get("rate")
				updated_json["basic_amount"]=item.get("rate")*item.get("qty")
				updated_json["amount"]= item.get("rate")*item.get("qty")
				updated_json["allow_zero_valuation"]= "0"
				#material_request_item
				args = {
					'item_code'	: item.get("item_code"),
					'warehouse'	: from_warehouse,
					'stock_qty'	: transfer_qty
				}
				payload= frappe._dict(args)
				serial_no =  get_serial_no(payload) #if  get_serial_no(payload).get("message") else ""
				if serial_no:
					serial_no = get_serial_no(payload).message
				else:
					serial_no = ""
				updated_json["serial_no"]=serial_no
				frappe.response["updated json"]=updated_json
				updated_dict.append(updated_json.copy())
				attended_to_arr.append(item.get("name"))
		stock_entry_doc.update(
			{
				"naming_series": "MAT-STE-.YYYY.-",
				"stock_entry_type":doc.get("material_request_type"),			
				"company": frappe.defaults.get_user_default("company"),	
				"from_warehouse":from_warehouse,
				"issued_to": frappe.db.get_value("Employee",{"user_id":doc.owner},"employee_number") or "-",
				"to_warehouse":	to_warehouse,
				"requisitioning_officer":	doc.get("owner"),	
				"requisitioning_time":	doc.get("creation"),
				"items": updated_dict
			}
		)
		stock_entry_doc.insert(ignore_permissions=True)
		for docname in attended_to_arr:
			frappe.db.set_value("Material Request Item", docname, "attended_to", "1")
		#frappe.msgprint(doclist)
def update_stock_entry_data(doc,state):
	issuing_officer = frappe.session.user
	current_timestamp  =frappe.utils.data.now_datetime()
	frappe.db.set_value("Stock Entry",doc.name,"issued_by", issuing_officer)
	frappe.db.set_value("Stock Entry",doc.name,"issued_on", current_timestamp)
@frappe.whitelist()
def procurement_method_on_select(material_request, supplier_name):
	#VALIDATE THIS MATERIAL REQUEST FIRST
	docstatus = frappe.db.get_value("Material Request",material_request,"docstatus")
	is_purchase = frappe.db.exists({
						"doctype":"Material Request",
						"name": material_request,
						"material_request_type": "Purchase"
						})
	if docstatus ==1 and  is_purchase:
		#GET ALL UNATTENDED MATERIAL REQUEST ITEMS (PURCHASE) FOR THIS MR
		mr_items_filtered = frappe.db.get_list("Material Request Item",
			filters={
			"docstatus": "1",
			"attended_to":"0",
			"parent": material_request
			},
			fields="`tabMaterial Request Item`.item_code, `tabMaterial Request Item`.item_name,`tabMaterial Request Item`.procurement_method, sum(`tabMaterial Request Item`.qty) as quantity, `tabMaterial Request Item`.ordered_qty, `tabMaterial Request Item`.item_group, `tabMaterial Request Item`.warehouse, `tabMaterial Request Item`.uom, `tabMaterial Request Item`.description, `tabMaterial Request Item`.parent",
			order_by="creation desc",
			ignore_permissions = True,
			as_list=False
		)
		#RETURN SUPPLIER OBJECT TOO
		supplier_json_object ={}
		supplier_full_set =[]
		contact = frappe.db.get_value("Dynamic Link", {"link_doctype":"Supplier", "link_title":supplier_name, "parenttype":"Contact"} ,"parent")
		email = frappe.db.get_value("Contact", contact, "email_id")
		supplier_json_object["supplier_name"]=supplier_name
		supplier_json_object["contact"]=contact
		supplier_json_object["email"]=email
		supplier_full_set.append(supplier_json_object)
		#PREPARE A JSON OBJECT FOR THE SINGLE MR WE HAVE
		mr_list_filtered=[material_request]
		#RETURN PAYLOAD NOW
		frappe.response["status"] ="valid"
		frappe.response["suppliers_for_group"] = supplier_full_set
		frappe.response["filtered_items"] =mr_items_filtered
		frappe.response["material_requests"] = mr_list_filtered

	else:
		frappe.response["status"] ="invalid"
		frappe.response["docstatus"] = docstatus


@frappe.whitelist()
def buyer_section_on_select(item_group):
	#item_group = frappe.form_dict.item_group

	#GET ALL UNATTENDED MATERIAL REQUEST ITEMS (PURCHASE,TRANSFER, ISSUE etc) FOR THIS GROUP ONLY
	unattended_item_codes = frappe.db.get_list("Material Request Item",
		filters={
		"docstatus": "1",
			"attended_to":"0",
			"item_group": item_group
		},
		fields=["item_code"],
		order_by="creation desc",
		ignore_permissions = True,
		as_list=False
	)
	if unattended_item_codes:
		#Now build an unattended array of non-awarded items only
		unnattended_arr =[]
		for unattended in unattended_item_codes:
			unawarded = frappe.db.exists({
						"doctype":"Item Default",
						"parent": unattended.item_code,
						"default_supplier": ""
						})
			if unawarded:
					unnattended_arr.append(unattended.item_code.copy())
		#BUILD A ITEMS PAYLOAD NOW
		mr_items_filtered = frappe.get_list("Material Request Item",
			filters={
				"docstatus": "1",
				"attended_to":"0",
				"item_group": item_group,
				"item_code": ["IN", unnattended_arr]
			},
			fields="`tabMaterial Request Item`.item_code, `tabMaterial Request Item`.item_name,`tabMaterial Request Item`.procurement_method, sum(`tabMaterial Request Item`.qty) as quantity, `tabMaterial Request Item`.ordered_qty, `tabMaterial Request Item`.item_group, `tabMaterial Request Item`.warehouse, `tabMaterial Request Item`.uom, `tabMaterial Request Item`.description, `tabMaterial Request Item`.parent",
			group_by="item_code",
			order_by="creation",
			#page_length=2000
			ignore_permissions = True,
			#as_list=False
		)
		#BUILD A MATERIAL REQUEST LIST PAYLOAD NOW
		mr_list_filtered = frappe.get_list("Material Request Item",
			filters={
				"docstatus": "1",
				"attended_to":"0",
				"item_group": item_group,
				"item_code": ["IN", unnattended_arr]
			},
			fields=["parent"],
			order_by="creation",
			#page_length=2000
			ignore_permissions = True,
			#as_list=False
		)
		
		#BUILD A PREQUALIFICATION SUPPLIER PAYLOAD
		
		#STEP 3 RETURN PREQUALIFICATION LIST FOR ITEM CATEGORY
		#===============================
		#GET SUPPLIERS FOR THIS ITEM GROUP AS WELL.
		suppliers_for_group = frappe.db.get_list("Prequalification Supplier",
			filters={
				"item_group_name": ["IN", item_group],
				"docstatus":"1"
			},
			fields=["supplier_name"],
			ignore_permissions = True,
			as_list=False
		)
		#=====================================================================================
		#GET SUPPLIERS WITH CONTACTS. REMOVE SUPPLIERS IF ITEMS EMPTY
		supplier_full_set = []
		supplier_json_object={}
		for supplier in suppliers_for_group:
			contact = frappe.db.get_value("Dynamic Link", {"link_doctype":"Supplier", "link_title":supplier.supplier_name, "parenttype":"Contact"} ,"parent")
			email = frappe.db.get_value("Contact", contact, "email_id")
			supplier_json_object["supplier_name"]=supplier.supplier_name
			supplier_json_object["contact"]=contact
			supplier_json_object["email"]=email
			supplier_full_set.append(supplier_json_object)
		
		frappe.response["suppliers_for_group"] = supplier_full_set
		frappe.response["filtered_items"] =mr_items_filtered
		frappe.response["material_requests"] = mr_list_filtered
	else:
		frappe.response["suppliers_for_group"] = ""
		frappe.response["filtered_items"] = ""
		frappe.response["material_requests"] = ""
@frappe.whitelist()
def send_tqe_action_email(document,rfq, item):
	#frappe.msgprint(doc)
	doc = frappe.get_doc("Tender Quotations Evaluations",document)
	bidders_awarded =frappe.db.get_list("Tender Quotation Evaluation Decision",
			filters={
			 "parent":document
			 } ,
			fields=["bidder"],
			ignore_permissions = True,
			as_list=False
		)
	bidders_list =[]
	for bid in bidders_awarded:
		bidders_list.append(bid.bidder)
	frappe.response["bids"]=bidders_list
	supplier_list = frappe.db.get_list("Supplier Quotation",
			filters={
				"name": ["IN", bidders_list],
				#"docstatus":"1"
			},
			fields=["supplier","contact_person"],
			ignore_permissions = True,
			as_list=False
		)
	supplier_regret_bids = frappe.db.get_list("Supplier Quotation Item",
			filters={
				"parent": ["NOT IN", bidders_list],
				"request_for_quotation": rfq
				#"docstatus":"1"
			},
			fields=["parent"],
			ignore_permissions = True,
			as_list=False
		)
	contacts =[]
	contacts_regret = get_regret_contacts(supplier_regret_bids)
	for supplier in supplier_list:
		contacts.append(supplier.contact_person)
	frappe.response["contacts"]=contacts
	awarded_emails = frappe.db.get_list("Contact",
			filters={
			 "name":["IN", contacts],
			 } ,
			fields=["email_id"],
			ignore_permissions = True,
			as_list=False
		)
	unawarded_emails = frappe.db.get_list("Contact",
			filters={
			 "name":["IN", contacts_regret],
			 } ,
			fields=["email_id"],
			ignore_permissions = True,
			as_list=False
		)
	frappe.response["emails"]=awarded_emails
	item_name = frappe.db.get_value("Item",item,"item_name")
	if not item_name:
		item_name = item
	recipients=[]
	recipients_regret =[]
	for userdata in awarded_emails:
		recipients.append(userdata.email_id)
	for userdata in unawarded_emails:
		recipients_regret.append(userdata.email_id)
	send_notifications(recipients,"Dear sir/madam. We would like to notify you that you have been awarded tender/quotation "+rfq+" for your bid on "+item_name+"\nTHIS IS NOT A PURCHASE ORDER","Notification of Award for "+rfq+"/"+item_name,doc.get("doctype"),document)
	send_notifications(recipients_regret,"Dear sir/madam, we regret to notify you that you have NOT been awarded tender/quotation "+rfq+" for your bid on "+item_name,"Notification of Regret for "+rfq+"/"+item_name,doc.get("doctype"),document)
def get_regret_contacts(supplier_regret_bids):
	supplier_list = frappe.db.get_list("Supplier Quotation",
			filters={
				"name": ["IN", supplier_regret_bids],
				#"docstatus":"1"
			},
			fields=["supplier","contact_person"],
			ignore_permissions = True,
			as_list=False
		)
	contacts =[]
	for supplier in supplier_list:
		contacts.append(supplier.contact_person)
	return contacts
def send_notifications(recipients, message,subject,doctype,docname):
	#template_args = get_common_email_args(None)
	email_args = {
				"recipients": recipients,
				"message": _(message),
				"subject": subject,
				"attachments": [frappe.attach_print(doctype, docname, file_name=docname)],
				"reference_doctype": doctype,
				"reference_name": docname,
				}
	#email_args.update(template_args)
	frappe.response["response"] = email_args
	enqueue(method=frappe.sendmail, queue='short', timeout=300, **email_args)
@frappe.whitelist()		
def auto_generate_purchase_order_using_cron():
	unattended_requests = frappe.db.get_list("Material Request",
			filters={
				"per_attended": ["<=", 99.99],
				"docstatus":"1",
				"material_request_type":"Purchase"
			},
			fields=["name"],
			ignore_permissions = True,
			as_list=False
		)
	the_list =[]
	for request in unattended_requests:
		material_request_number = request.name
		the_list.append(material_request_number)
		doc = frappe.get_doc ("Material Request", material_request_number)
		auto_generate_purchase_order_by_material_request(doc,"Submitted")
	frappe.response["thelist"] = the_list
#@frappe.whitelist(allow_guest =True)		
def raise_tqe(doc, state):
	#The RFQ tied to this sq
	parent  = doc.request_for_quotation
	if parent:
		#"CHECK IF AN EVALUATION FOR THIS RFQ/TENDER HAS BEEN ENTERED."
		exists = frappe.db.exists({
					"doctype":"Tender Quotation Evaluation",
					"rfq_no": parent,
				})
		if not exists:
			#Do a date comparison to check whether opening date has arrived
			print("Starting...")
@frappe.whitelist()
def dispatch_order(doc, state):
	doc = json.loads(doc)
	supplier_name = doc.get("supplier")
	contact = frappe.db.get_value("Dynamic Link", {"link_doctype":"Supplier", "link_title":supplier_name, "parenttype":"Contact"} ,"parent")
	email = frappe.db.get_value("Contact", contact, "email_id")
	if email:
		if not frappe.db.exists("User", email):
			user = frappe.get_doc({
					'doctype': 'User',
					'send_welcome_email': 1,
					'email': email,
					'first_name': supplier_name,
					'user_type': 'Website User'
					#'redirect_url': link
				})
			user.save(ignore_permissions=True)
		from frappe.utils import get_url, cint
		url = get_url("/purchase-orders/" + doc.get("name"))
		recipients =[email]
		order_expiry = doc.get("schedule_date") or add_days(nowdate(), 30)
		send_notifications(recipients, """Dear {0} please find the attached purchase order for your action. Please click on this link {1} to access the order so that you can fill in your e-delivery. Expiry date of this order is on  {2}. 
						Terms and Conditions apply""".format(supplier_name,url,order_expiry),"You have a new Purchase Order - {0} !".format(doc.get("name")),"Purchase Order", doc.get("name"))
		#send notifications
		frappe.db.set_value("Purchase Order", doc.get("name"), "schedule_date", order_expiry)
		frappe.response["expiry"] = order_expiry
		frappe.response["nowdate"] = nowdate()
		frappe.response["order"] = doc.get("name")
		frappe.msgprint("Order dispatched to {0}".format(supplier_name))
	else:
		recepients =[]
		for user in frappe.db.get_list("User",
			filters={
				"enabled": "1",	
				"email":["NOT IN",["erp@mtrh.go.ke","guest@example.com"]],	
			},
			fields=["email"],
			ignore_permissions = True,
			as_list=False
		):	
			#frappe.msgprint(user.email)
			user = frappe.get_doc("User", user.email)
			if user and "System Manager" in user.get("roles"):
				recepients.append(user.get("email"))
		#if recepients:
		send_notifications(recepients, "The contact details of the following supplier has not been added into the system. Please update the details to facilitate prompt notifications: {0}".format(supplier_name),"URGENT: Supplier Contact Update for {0}".format(supplier_name),"Supplier", supplier_name)
		frappe.throw("The supplier contact e-mail has not been set and therefore the supplier was not alerted. We have alerted the Supply Chain Manager and their team to follow up on the issue")



