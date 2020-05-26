// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

window.doc={{ doc.as_json() }};

$(document).ready(function() {
	new order();
	window.doc_info = {
		customer: '{{doc.customer}}',
		doctype: '{{ doc.doctype }}',
		doctype_name: '{{ doc.name }}',
		grand_total: '{{ doc.grand_total }}',
		currency: '{{ doc.currency }}'
	}
});

order = Class.extend({
	init: function(){
		this.onfocus_select_all();
		this.change_qty();
		this.change_rate();
		this.change_quantity_amount();
		this.terms();
		this.generatedeliverynote();
		this.navigate_quotations();
		this.change_attachments();
	},

	onfocus_select_all: function(){
		$("input").click(function(){
			$(this).select();
		})
	},
	
	change_attachments: function(){
		var me = this;
		$('.rfq-items').on("change", ".rfq-attachments", function(){
			me.attachments = $(this).val();
			console.log("ATTACHED: " + me.attachments);
			
			$.each(doc.items, function(idx, data){
				if(data.idx == me.idx){
					data.attachments = me.attachments;
				}
			})
		})
	},

	change_qty: function(){
		var me = this;
		$('.rfq-items').on("change", ".rfq-qty", function(){
			me.idx = parseFloat($(this).attr('data-idx'));
			me.qty = parseFloat($(this).val()) || 0;
			me.rate = parseFloat($(repl('.rfq-rate[data-idx=%(idx)s]',{'idx': me.idx})).val());
			me.update_qty_rate();
			$(this).val(format_number(me.qty, doc.number_format, 2));
			me.attachments = $(this).data("attachments");
		})
	},

	change_rate: function(){
		var me = this;
		$(".rfq-items").on("change", ".rfq-rate", function(){
			me.idx = parseFloat($(this).attr('data-idx'));
			me.rate = parseFloat($(this).val()) || 0;
			me.qty = parseFloat($(repl('.rfq-qty[data-idx=%(idx)s]',{'idx': me.idx})).val());
			me.update_qty_rate();
			$(this).val(format_number(me.rate, doc.number_format, 2));
		})
	},
	change_quantity_amount: function(){
		var me = this;		
		$(".order-items").on("change", ".order-supply", function(){			
			me.idx = parseFloat($(this).attr('data-idx'));	
			//alert(me.idx)		
			me.tosupply = parseFloat($(this).val()) || 0;
			me.qty = parseFloat($(repl('.order-qty[data-idx=%(idx)s]',{'idx': me.idx})).val());
			me.rate = parseFloat($(repl('.orderrate[data-idx=%(idx)s]',{'idx': me.idx})).val());
			me.dnote = parseFloat($(repl('.orderdnote[data-idx=%(idx)s]',{'idx': me.idx})).val());
			//me.rate = parseFloat($(this).val()) || 0;			
			//me.rate = "55"
			//parseFloat($(repl('.orderrate[data-idx=%(idx)s]',{'idx': me.idx})).val())		
			//alert(me.dnote)
			//me.qty = parseFloat($(repl('.order-qty[data-idx=%(idx)s]',{'idx': me.idx})).val());	
			//alert(me.rate)					
			me.update_supply_amount();
			//$(this).val(format_number(me.rate, doc.number_format, 2));
		})
	},

	terms: function(){
		$(".terms").on("change", ".terms-feedback", function(){
			doc.terms = $(this).val();
		})
	},

	update_supply_amount: function(){
		var me = this;
		doc.grand_total = 0.0;
		$.each(doc.items, function(idx, data){
			if(data.idx == me.idx){				
				data.qty = me.qty;
				data.tosupply=me.tosupply;
				data.rate = me.rate;
				//alert(data.rate)
				data.amount = (me.rate * me.tosupply) || 0.0;
				//alert(data.amount )
				$(repl('.order-amount[data-idx=%(idx)s]',{'idx': me.idx})).text(format_number(data.amount, doc.number_format, 2));
				//data.attachments = me.attachments;
						}
			doc.grand_total += flt(data.amount);
			$('.tax-grand-total').text(format_number(doc.grand_total, doc.number_format, 2));
			
		})
	},

	update_qty_rate: function(){
		var me = this;
		doc.grand_total = 0.0;
		$.each(doc.items, function(idx, data){
			if(data.idx == me.idx){				
				data.qty = me.qty;
				data.tosupply=me.tosupply;
				data.rate = me.rate;
				
				//alert(data.rate)
				data.amount = (me.rate * me.tosupply) || 0.0;
				//alert(data.amount )
				$(repl('.order-amount[data-idx=%(idx)s]',{'idx': me.idx})).text(format_number(data.amount, doc.number_format, 2));
				//data.attachments = me.attachments;
						}

			doc.grand_total += flt(data.amount);
			$('.tax-grand-total').text(format_number(doc.grand_total, doc.number_format, 2));
			
		})
	},

	generatedeliverynote: function(){		
		
		$('.btn-gen').click(function(){			
			var isconfirmed = confirm("Ensure you have entered all field required Are you sure?");
			if(isconfirmed){
				//frappe.freeze();
				frappe.call({
					type: "POST",
					method: "mtrh_dev.mtrh_dev.tqe_evaluation.Generate_Purchase_Receipt_Draft",
					args: {						
						doc:doc							

					},
					btn: this,
					callback: function(r){
						frappe.unfreeze();
						if(r.message){
							$('.btn-sm').hide()
							//window.location.href = "/supplier-quotations/" + encodeURIComponent(r.message);
							//window.location.replace("/supplier-quotations/" + encodeURIComponent(r.message));
							frappe.show_alert("Your submission has been successfull", 10)
						}
					}
				})
			}
		})
	},

	navigate_quotations: function() {
		$('.quotations').click(function(){
			name = $(this).attr('idx')
			window.location.href = "/quotations/" + encodeURIComponent(name);
		})
	}
})
