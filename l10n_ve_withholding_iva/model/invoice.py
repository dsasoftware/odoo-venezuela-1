#!/usr/bin/python
# -*- encoding: utf-8 -*-
###########################################################################
#    Module Writen to OpenERP, Open Source Management Solution
#    Copyright (C) OpenERP Venezuela (<http://openerp.com.ve>).
#    All Rights Reserved
###############Credits######################################################
#    Coded by: Vauxoo C.A.           
#    Planified by: Nhomar Hernandez
#    Audited by: Vauxoo C.A.
#############################################################################
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
################################################################################

import time
from openerp.osv import fields, osv
from openerp.addons import decimal_precision as dp
from openerp.tools.translate import _


class account_invoice(osv.osv):
    _inherit = 'account.invoice'
    def _retenida(self, cr, uid, ids, name, args, context):
        res = {}
        if context is None:
            context = {}
        for id in ids:
            res[id] = self.test_retenida(cr, uid, [id])
        return res


    def _get_inv_from_line(self, cr, uid, ids, context={}):
        context = context or {}
        move = {}
        for line in self.pool.get('account.move.line').browse(cr, uid, ids):
            if line.reconcile_partial_id:
                for line2 in line.reconcile_partial_id.line_partial_ids:
                    move[line2.move_id.id] = True
            if line.reconcile_id:
                for line2 in line.reconcile_id.line_id:
                    move[line2.move_id.id] = True
        invoice_ids = []
        if move:
            invoice_ids = self.pool.get('account.invoice').search(cr, uid, [('move_id','in',move.keys())], context=context)
        return invoice_ids

    def _get_inv_from_reconcile(self, cr, uid, ids, context={}):
        context = context or {}
        move = {}
        for r in self.pool.get('account.move.reconcile').browse(cr, uid, ids):
            for line in r.line_partial_ids:
                move[line.move_id.id] = True
            for line in r.line_id:
                move[line.move_id.id] = True
        
        invoice_ids = []
        if move:
            invoice_ids = self.pool.get('account.invoice').search(cr, uid, [('move_id','in',move.keys())], context=context)
        return invoice_ids

        
    _columns = {
        'wh_iva': fields.function(_retenida, method=True, string='Withhold', type='boolean',
            store={
                'account.invoice': (lambda self, cr, uid, ids, c={}: ids, None, 50),
                'account.move.line': (_get_inv_from_line, None, 50),
                'account.move.reconcile': (_get_inv_from_reconcile, None, 50),
            }, help="The account moves of the invoice have been retention with account moves of the payment(s)."),    
        'wh_iva_rate': fields.float('Wh rate', digits_compute= dp.get_precision('Withhold'), readonly=True, states={'draft':[('readonly',False)]}, help="Withholding vat rate"),
        'wh_iva_id': fields.many2one('account.wh.iva', 'Wh. Vat', readonly=True, help="Withholding vat."),        
        'vat_apply':fields.boolean('Exclude this document from VAT Withholding', help="This selection indicates whether generate the invoice withholding document")
    }


    def onchange_partner_id(self, cr, uid, ids, type, partner_id,
            date_invoice=False, payment_term=False, partner_bank_id=False, company_id=False):

        data = super(account_invoice, self).onchange_partner_id(cr, uid, ids, type, partner_id,
            date_invoice, payment_term, partner_bank_id, company_id)
        if partner_id:
            part = self.pool.get('res.partner').browse(cr, uid, partner_id)
            data[data.keys()[0]]['wh_iva_rate'] =  part.wh_iva_rate
        return data


    def create(self, cr, uid, vals, context={}):
        context = context or {}
        partner_id = vals.get('partner_id',False)
        if partner_id:
            partner = self.pool.get('res.partner').browse(cr, uid,partner_id)
            vals['wh_iva_rate'] = partner.wh_iva_rate
        return super(account_invoice, self).create(cr, uid, vals, context)

    def copy(self, cr, uid, id, default=None, context=None):
        context = context or {}
        if default is None:
            default = {}
        default = default.copy()
        #TODO: PROPERLY CALL THE WH_IVA_RATE
        default.update({'wh_iva':False, 'wh_iva_id':False, 'vat_apply': False})
        return super(account_invoice, self).copy(cr, uid, id, default, context)

    def test_retenida(self, cr, uid, ids, *args):     
        type2journal = {'out_invoice': 'iva_sale', 'in_invoice': 'iva_purchase', 'out_refund': 'iva_sale', 'in_refund': 'iva_purchase'}
        type_inv = self.browse(cr, uid, ids[0]).type
        type_journal = type2journal.get(type_inv, 'iva_purchase')      
        res = self.ret_payment_get(cr, uid, ids)
        if not res:
            return False
        ok = True

        cr.execute('select \
                l.id \
            from account_move_line l \
                inner join account_journal j on (j.id=l.journal_id) \
            where l.id in ('+','.join(map(str,res))+') and j.type='+ '\''+type_journal+'\'')
        ok = ok and  bool(cr.fetchone())
        return ok


    def wh_iva_line_create(self, cr, uid, inv):
        wh_iva_rate = inv.type in ('in_invoice', 'in_refund') and inv.partner_id.wh_iva_rate or inv.type in ('out_invoice', 'out_refund') and inv.company_id.partner_id.wh_iva_rate
        return (0, False, {
            'name': inv.name or inv.number,
            'invoice_id': inv.id,
            'wh_iva_rate': wh_iva_rate,
        })

    def action_wh_iva_supervisor(self, cr, uid, ids, *args):
        user_obj= self.pool.get('res.users')
        user_brw= user_obj.browse(cr,uid,uid)
        print 
        for inv in self.browse(cr, uid, ids):
            if inv.amount_total==0.0 and inv.currency_id.id != user_brw.company_id.currency_id.id:
                raise osv.except_osv('Invalid Action !', _('The currency of the invoice does not match with the currency of the company. Check this please'))

            elif inv.amount_total==0.0 or inv.currency_id.id != user_brw.company_id.currency_id.id:
                if inv.amount_total==0.0:
                    raise osv.except_osv('Invalid Action !', _('This invoice has total amount %s %s check the products price')%(inv.amount_total,inv.currency_id.symbol))
                elif inv.currency_id.id != user_brw.company_id.currency_id.id:
                    raise osv.except_osv('Invalid Action !', _('The currency of the invoice does not match with the currency of the company. Check this please'))
        return True


    def action_wh_iva_create(self, cr, uid, ids, *args):
        wh_iva_obj = self.pool.get('account.wh.iva')
        for inv in self.browse(cr, uid, ids):
            if inv.wh_iva_id:
                #raise osv.except_osv('Invalid Action !', _('This invoice is already withholded'))
                return 0
            ret_line = []
            if inv.type in ('out_invoice', 'out_refund'):
                acc_id = inv.partner_id.property_account_receivable.id
                wh_type = 'out_invoice'
            else:
                acc_id = inv.partner_id.property_account_payable.id
                wh_type = 'in_invoice'
                if not acc_id:
                    raise osv.except_osv('Invalid Action !',\
            _('You need to configure the partner with withholding accounts!'))
            
            ret_line.append(self.wh_iva_line_create(cr, uid, inv))
            ret_iva = {
                'name':_('ORIGIN %s'%(inv.number)),
                'type': wh_type,
                'account_id': acc_id,
                'partner_id': inv.partner_id.id,
                'wh_lines':ret_line
            }
            ret_id = wh_iva_obj.create(cr, uid, ret_iva)
            self.write(cr, uid, [inv.id], {'wh_iva_id':ret_id})
        return ret_id

    def button_reset_taxes_ret(self, cr, uid, ids, context=None):
        if not context:
            context = {}

        ait_obj = self.pool.get('account.invoice.tax')
        for id in ids:
            amount_tax_ret = {}
            amount_tax_ret = ait_obj.compute_amount_ret(cr, uid, id, context)
            for ait_id in amount_tax_ret.keys():
                ait_obj.write(cr, uid, ait_id, amount_tax_ret[ait_id])

        return True

    def button_reset_taxes(self, cr, uid, ids, context=None):
        context = context or {}
        super(account_invoice, self).button_reset_taxes(cr, uid, ids, context)
        self.button_reset_taxes_ret(cr, uid, ids, context)
        
        return True

    def _withholding_partner(self, cr, uid, ids, context=None):  
        if context is None:
            context={}
        obj = self.browse(cr, uid, ids[0],context=context)
        #No create withholding vat for customer invoice
#        if obj.type in ('out_invoice', 'out_refund') and obj.partner_id.wh_iva_agent:
#            return True
        if obj.type in ('in_invoice', 'in_refund') and obj.company_id.partner_id.wh_iva_agent:
            return True 
        return False

    def _withholdable_tax(self, cr, uid, ids, context=None):
        if context is None:
            context={}
        return any([line.tax_id.ret for line in self.browse(cr, uid, ids[0], context=context).tax_line])

    def check_withholdable(self, cr, uid, ids, context=None):
        '''
        This will test for Refund invoice trying to find out
        if its regarding parent is in the same fortnight.
        
        return True if invoice is type 'in_invoice'
        return True if invoice is type 'in_refund' and parent_id invoice
                are both in the same fortnight.
        return False otherwise
        '''
        per_obj = self.pool.get('account.period')
        if context is None:
            context={}
        inv_brw = self.browse(cr,uid,ids[0],context=context)
        if inv_brw.type == 'in_invoice':
            return True
        if inv_brw.type == 'in_refund' and inv_brw.parent_id:
            dt_refund = inv_brw.date_invoice or time.strftime('%Y-%m-%d')
            dt_invoice = inv_brw.parent_id.date_invoice
            return  per_obj.find_fortnight(cr, uid, dt=dt_refund, context=context) == \
                    per_obj.find_fortnight(cr, uid, dt=dt_invoice, context=context)
        return False

    def check_wh_apply(self, cr, uid, ids, context=None):
        if context is None:
            context={}
        invo_brw = self.browse(cr,uid,ids[0],context=context)
        if invo_brw.vat_apply:
            return False
        wh_apply=[]
        wh_apply.append(self._withholdable_tax(cr, uid, ids, context=context))
        wh_apply.append(self._withholding_partner(cr, uid, ids, context=context))
        return all(wh_apply)

    def _get_move_lines(self, cr, uid, ids, to_wh, period_id, 
                            pay_journal_id, writeoff_acc_id, 
                            writeoff_period_id, writeoff_journal_id, date, 
                            name, context=None):
        if context is None: context = {}
        res = super(account_invoice,self)._get_move_lines(cr, uid, ids, to_wh, period_id, 
                            pay_journal_id, writeoff_acc_id, 
                            writeoff_period_id, writeoff_journal_id, date, 
                            name, context=context)
        if context.get('vat_wh',False):
            invoice = self.browse(cr, uid, ids[0])
            
            types = {'out_invoice': -1, 'in_invoice': 1, 'out_refund': 1, 'in_refund': -1}
            direction = types[invoice.type]

            for tax_brw in to_wh:
                if 'invoice' in invoice.type:
                    acc = tax_brw.tax_id.wh_vat_collected_account_id and tax_brw.tax_id.wh_vat_collected_account_id.id or False
                elif 'refund' in invoice.type:
                    acc = tax_brw.tax_id.wh_vat_paid_account_id and tax_brw.tax_id.wh_vat_paid_account_id.id or False
                if not acc:
                    raise osv.except_osv(_('Missing Account in Tax!'),_("Tax [%s] has missing account. Please, fill the missing fields") % (tax_brw.tax_id.name,))
                res.append((0,0,{
                    'debit': direction * tax_brw.amount_ret<0 and - direction * tax_brw.amount_ret,
                    'credit': direction * tax_brw.amount_ret>0 and direction * tax_brw.amount_ret,
                    'account_id': acc,
                    'partner_id': invoice.partner_id.id,
                    'ref':invoice.number,
                    'date': date,
                    'currency_id': False,
                    'name':name
                }))
        
        return res

    def validate_wh_iva_done(self, cr, uid, ids, context=None):
        """
        Method that check if wh vat is validated in invoice refund.
        @params: ids: list of invoices.
        return: True: the wh vat is validated.
                False: the wh vat is not validated.
        """
        context = context or {}
        for inv in self.browse(cr, uid, ids, context=context):
            if inv.type in ('out_invoice', 'out_refund') and not inv.wh_iva_id:
                riva = True
            else:
                riva = not inv.wh_iva_id and True or inv.wh_iva_id.state in ('done') and True or False
                if not riva:
                    raise osv.except_osv(_('Error !'), \
                                     _('The withholding VAT "%s" is not validated!' % inv.wh_iva_id.code ))
                    return False
        return True

account_invoice()

class account_invoice_tax(osv.osv):
    _inherit = 'account.invoice.tax'
    _columns = {
        'amount_ret': fields.float('Withholding amount', digits_compute= dp.get_precision('Withhold'), help="Withholding vat amount"),
        'base_ret': fields.float('Amount', digits_compute= dp.get_precision('Withhold'), help="Amount without tax"),
    }

    def compute_amount_ret(self, cr, uid, invoice_id, context={}):
        context = context or {}
        res = {}
        inv = self.pool.get('account.invoice').browse(cr, uid, invoice_id, context)

        for ait in inv.tax_line:
            amount_ret = 0.0
            if ait.tax_id.ret:
                amount_ret = inv.wh_iva_rate and ait.tax_amount*inv.wh_iva_rate/100.0 or 0.00
            res[ait.id] = {'amount_ret': amount_ret, 'base_ret': ait.base_amount}
        return res

account_invoice_tax()
