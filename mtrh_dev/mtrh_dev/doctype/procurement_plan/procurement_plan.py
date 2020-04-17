# -*- coding: utf-8 -*-
# Copyright (c) 2020, MTRH and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import msgprint
from frappe.utils import cint, flt, cstr, now
from frappe.model.document import Document

class ProcurementPlan(Document):
	pass
@frappe.whitelist()
def procurement_consumption_mrq(year_start, year_end,item_code, department_name):
	#msgprint("I have run again") 
	total_qty =frappe.db.sql("""SELECT sum(qty) FROM `tabMaterial Request Item` WHERE creation BETWEEN %s AND %s
	AND item_code = %s AND upper(department) = %s AND docstatus=1;""",(year_start,year_end,item_code,department_name.upper()))
	#msgprint(total_qty[0][0])
	return flt(total_qty[0][0]) if total_qty else 0.0
@frappe.whitelist()
def procurement_plan_bal_mrq(year_start, year_end,item_code, department_name, fiscal_year):
	#msgprint("I have run again") 
	total_qty =frappe.db.sql("""SELECT coalesce(sum(qty),0) FROM `tabMaterial Request Item` WHERE creation BETWEEN %s AND %s
	AND item_code = %s AND upper(department) = %s AND docstatus=1;""",(year_start,year_end,item_code,department_name.upper()))
	procurement_plan_amt = frappe.db.sql("""SELECT coalesce(sum(qty),0) FROM `tabProcurement Plan Item` WHERE docstatus=1 AND item_code=%s AND upper(department_name)=%s 
		AND fs_yr=%s """,(item_code,department_name.upper(),fiscal_year))
	procurement_plan_balance = procurement_plan_amt[0][0]-total_qty[0][0]
	#msgprint(flt(total_qty[0][0]))
	return procurement_plan_balance
@frappe.whitelist()
def getsumpendingsubmittedpurchaseorder(year_start, year_end,department):
        
        totalpendingsubmitted =frappe.db.sql("""SELECT sum(qty) FROM `tabPurchase Order Item` WHERE creation BETWEEN %s AND %s
        AND upper(department) = %s AND docstatus!=2;""",(year_start,year_end,department.upper()))
        
        return flt(totalpendingsubmitted[0][0]) if totalpendingsubmitted else 0.0
