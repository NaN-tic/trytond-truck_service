#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from decimal import Decimal
from sql.aggregate import Sum
from sql.conditionals import Coalesce

from trytond.pool import Pool, PoolMeta
from trytond.model import Workflow, ModelSQL, ModelView, fields
from trytond.pyson import Eval, If, In
from trytond.tools import reduce_ids
from trytond.transaction import Transaction

__all__ = ['Order', 'Invoice', 'InvoiceLine']
__metaclass__ = PoolMeta


_STATES = {
    'readonly': Eval('state') != 'draft',
}
_DEPENDS = ['state']


class Order(Workflow, ModelSQL, ModelView):
    'Truck Order'
    __name__ = 'truck.order'
    _rec_name = 'reference'
    company = fields.Many2One('company.company', 'Company', required=True,
        domain=[
            ('id', If(In('company', Eval('context', {})), '=', '!='),
                Eval('context', {}).get('company', -1)),
            ],
        states=_STATES, depends=_DEPENDS)
    currency_digits = fields.Function(fields.Integer('Currency Digits'),
        'on_change_with_currency_digits')
    code = fields.Char("Code", size=None, select=True, readonly=True)
    reference = fields.Char("Reference", size=None, select=True,
        states=_STATES, depends=_DEPENDS)
    party = fields.Many2One('party.party', 'Customer', required=True,
        states=_STATES, depends=_DEPENDS)
    project = fields.Many2One('party.project',
        'Project',
        domain=[
            ('party', '=', Eval('party'))
            ],
        states=_STATES, depends=_DEPENDS + ['party'])
    invoice_address = fields.Many2One('party.address',
        'Invoice Address', required=True,
        domain=[
            ('party', '=', Eval('party'))
            ],
        states=_STATES, depends=_DEPENDS + ['party'])
    delivery_address = fields.Many2One('party.address',
        'Delivery Address', required=True,
        domain=[
            ('party', '=', Eval('party'))
            ],
        states=_STATES, depends=_DEPENDS + ['party'])
    order_date = fields.Date('Order Date', required=True, states=_STATES,
        depends=_DEPENDS)
    start_time = fields.DateTime('Start Date',
        states={
            'required': Eval('state') == 'processing',
            'readonly': ~Eval('state').in_(['draft', 'confirmed']),
            },
        depends=_DEPENDS)
    end_time = fields.DateTime('End Date',
        states={
            'required': Eval('state') == 'recieved',
            'readonly': ~Eval('state').in_(['draft', 'confirmed',
                    'processing']),
            },
        depends=_DEPENDS)
    notes = fields.Text('Notes', required=True, states=_STATES,
        depends=_DEPENDS)
    vehicle = fields.Many2One('asset.vehicle', 'Vehicle', required=True,
        states=_STATES, depends=_DEPENDS)
    driver = fields.Many2One('company.employee', 'Driver',
        states=_STATES, depends=_DEPENDS)
    payment_term = fields.Many2One('account.invoice.payment_term',
        'Payment Term', required=True, states=_STATES, depends=_DEPENDS)
    quantity = fields.Float('Quantity', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    unit_price = fields.Numeric('Unit Price', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    traffic_taxes = fields.Numeric('Trafic Taxes', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    discount = fields.Numeric('Discount', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    various = fields.Numeric('Various', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    tax = fields.Many2One('account.tax', 'Tax', ondelete='RESTRICT',
        domain=[
            ('parent', '=', None),
            ['OR',
                ('group', '=', None),
                ('group.kind', 'in', ['sale', 'both'])
                ],
            ],
        states=_STATES, depends=_DEPENDS)
    untaxed_amount = fields.Function(fields.Numeric('Untaxed',
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits']),
        'get_amount', searcher='search_untaxed_amount')
    tax_amount = fields.Function(fields.Numeric('Tax', digits=(16,
                Eval('currency_digits', 2)), depends=['currency_digits']),
        'get_amount', searcher='search_tax_amount')
    total_amount = fields.Function(fields.Numeric('Total', digits=(16,
                Eval('currency_digits', 2)), depends=['currency_digits']),
        'get_amount', searcher='search_total_amount')
    invoices = fields.Function(fields.One2Many('account.invoice', None,
            'Invoices'),
        'get_invoices')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('recieved', 'Recieved'),
        ('done', 'Done'),
        ('cancel', 'Canceled'),
        ('refused', 'Refused'),
        ], 'State', readonly=True)

    @classmethod
    def __setup__(cls):
        super(Order, cls).__setup__()
        cls._order.insert(0, ('order_date', 'DESC'))
        cls._order.insert(1, ('id', 'DESC'))
        cls._error_messages.update({
                'delete_cancel': ('Truck Order "%s" must be cancelled before'
                    ' deletion.'),
                'no_sequence': ('There is no Truck Order sequence. Please '
                    'define one in configuration.'),
                'missing_account_revenue': ('Product "%(product)s" of vehicle'
                    ' %(vehicle)s misses a revenue account.'),
                })
        cls._transitions |= set((
                ('draft', 'confirmed'),
                ('confirmed', 'processing'),
                ('processing', 'processing'),
                ('processing', 'recieved'),
                ('recieved', 'done'),
                ('draft', 'cancel'),
                ('draft', 'refused'),
                ('confirmed', 'cancel'),
                ('cancel', 'draft'),
                ))
        cls._buttons.update({
                'draft': {
                    'invisible': Eval('state') != 'cancel',
                    'icon': 'tryton-clear',
                    },
                'confirm': {
                    'invisible': Eval('state') != 'draft',
                    'icon': 'tryton-ok',
                    },
                'process': {
                    'invisible': Eval('state') != 'confirmed',
                    'icon': 'tryton-go-next',
                    },
                'recieve': {
                    'invisible': Eval('state') != 'processing',
                    'icon': 'tryton-ok',
                    },
                'done': {
                    'invisible': Eval('state') != 'recieved',
                    'icon': 'tryton-ok',
                    },
                'refuse': {
                    'invisible': Eval('state') != 'draft',
                    'icon': 'tryton-cancel',
                    },
                'cancel': {
                    'invisible': ~Eval('state').in_(['draft', 'confirmed']),
                    'icon': 'tryton-cancel',
                    },
                })

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_currency_digits():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.digits
        return 2

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_quantity():
        return 0.0

    @staticmethod
    def default_discount():
        return Decimal('0')

    @staticmethod
    def default_traffic_taxes():
        return Decimal('0')

    @classmethod
    def default_payment_term(cls):
        PaymentTerm = Pool().get('account.invoice.payment_term')
        payment_terms = PaymentTerm.search(cls.payment_term.domain)
        if len(payment_terms) == 1:
            return payment_terms[0].id

    @staticmethod
    def default_various():
        return Decimal('0')

    @fields.depends('company')
    def on_change_with_currency_digits(self, name=None):
        if self.company:
            return self.company.currency.digits
        return 2

    @fields.depends('party')
    def on_change_party(self):
        changes = {}
        invoice_address = None
        delivery_address = None
        payment_term = None
        if self.party:
            invoice_address = self.party.address_get(type='invoice')
            try:
                #Delivery address may not exist
                delivery_address = self.party.address_get(type='delivery')
            except AttributeError:
                delivery_address = self.party.address_get()
            if self.party.customer_payment_term:
                payment_term = self.party.customer_payment_term
        if invoice_address:
            changes['invoice_address'] = invoice_address.id
            changes['invoice_address.rec_name'] = invoice_address.rec_name
        else:
            changes['invoice_address'] = None
        if delivery_address:
            changes['delivery_address'] = delivery_address.id
            changes['delivery_address.rec_name'] = delivery_address.rec_name
        else:
            changes['delivery_address'] = None
        if payment_term:
            changes['payment_term'] = payment_term.id
            changes['payment_term.rec_name'] = payment_term.rec_name
        return changes

    @fields.depends('project', 'invoice_address')
    def on_change_project(self):
        changes = {}
        if (self.project and self.project.invoice_address and
                self.project.invoice_address != self.invoice_address):
            invoice_address = self.project.invoice_address
            changes['invoice_address'] = invoice_address.id
            changes['invoice_address.rec_name'] = invoice_address.rec_name
        return changes

    @fields.depends('vehicle')
    def on_change_vehicle(self):
        changes = {}
        if self.vehicle:
            product = self.vehicle.asset.product
            changes['unit_price'] = product.list_price
            if product.customer_taxes:
                changes['tax'] = product.customer_taxes[0].id
                changes['tax.rec_name'] = product.customer_taxes[0].rec_name
            if self.vehicle.driver:
                changes['driver'] = self.vehicle.driver.id
                changes['driver.rec_name'] = self.vehicle.driver.rec_name
        return changes

    @classmethod
    def get_amount(cls, orders, names):
        pool = Pool()
        Tax = pool.get('account.tax')
        untaxed_amount = {}.fromkeys([o.id for o in orders], Decimal('0.0'))
        tax_amount = {}.fromkeys([o.id for o in orders], Decimal('0.0'))
        total_amount = {}.fromkeys([o.id for o in orders], Decimal('0.0'))
        for order in orders:
            gross = (Decimal(str(order.quantity or 0.0)) * order.unit_price
                + order.various)
            untaxed = gross - (order.discount * gross / 100)
            if order.tax:
                val, = Tax.compute([order.tax], untaxed, 1.0)
            else:
                val = {'amount': Decimal('0.0')}
            tax_amount[order.id] = Decimal(val['amount']).quantize(
                    Decimal(str(10 ** - order.currency_digits)))
            untaxed_amount[order.id] = Decimal(untaxed).quantize(
                    Decimal(str(10 ** - order.currency_digits)))
            total_amount[order.id] = Decimal(untaxed + val['amount'] + (
                    order.traffic_taxes or Decimal('0.0'))).quantize(
                        Decimal(str(10 ** - order.currency_digits)))

        result = {
            'untaxed_amount': untaxed_amount,
            'tax_amount': tax_amount,
            'total_amount': total_amount,
            }
        for key in result.keys():
            if key not in names:
                del result[key]
        return result

    @classmethod
    def get_invoices(cls, orders, name):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        result = {}.fromkeys([o.id for o in orders], [])
        lines = InvoiceLine.search([
                ('origin.id', 'in', [o.id for o in orders], 'truck.order'),
                ])

        for line in lines:
            order = line.origin.id
            invoice = line.invoice.id
            if not invoice in result[order]:
                result[order].append(invoice)
        return result

    def create_invoice(self):
        'Return the invoice to create for the given order'
        pool = Pool()
        Journal = pool.get('account.journal')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')
        with Transaction().set_user(0):
            invoice = Invoice()
            invoice_line = InvoiceLine()
        # TODO: generate invoice
        invoice.company = self.company
        invoice.currency = self.company.currency
        invoice.type = 'out_invoice'
        invoice.party = self.party
        for key, value in invoice.on_change_party().iteritems():
            setattr(invoice, key, value)
        invoice.payment_term = self.payment_term
        invoice.invoice_address = self.invoice_address
        journals = Journal.search([
                ('type', '=', 'revenue'),
                ], limit=1)
        if journals:
            journal, = journals
            invoice.journal = journal

        invoice_line.type = 'line'
        invoice_line.description = self.notes or ''
        invoice_line.party = self.party
        invoice_line.quantity = 1.0
        invoice_line.gross_unit_price = (Decimal(str(self.quantity or 0.0)) *
            self.unit_price + self.various)
        invoice_line.discount = self.discount * Decimal('.01')
        invoice_line.unit_price = invoice_line.update_prices()['unit_price']
        invoice_line.traffic_taxes = self.traffic_taxes
        invoice_line.origin = self

        product = self.vehicle.asset.product
        invoice_line.product = product
        invoice_line.unit = product.default_uom
        invoice_line.account = product.account_revenue_used
        if not invoice_line.account:
            self.raise_user_error('missing_account_revenue', {
                    'vehicle': self.vehicle.rec_name,
                    'product': product.rec_name,
                    })
        invoice_line.taxes = [self.tax]
        invoice.lines = [invoice_line]
        invoice.save()
        with Transaction().set_user(0, set_context=True):
            Invoice.update_taxes([invoice])

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Config = pool.get('truck.configuration')

        vlist = [x.copy() for x in vlist]
        config = Config(1)
        if not config.order_sequence:
            cls.raise_user_error('no_sequence')
        for values in vlist:
            values['code'] = Sequence.get_id(config.order_sequence.id)
        return super(Order, cls).create(vlist)

    @classmethod
    def delete(cls, orders):
        cls.cancel(orders)
        for order in order:
            if order.state != 'cancel':
                cls.raise_user_error('delete_cancel', (order.rec_name,))
        super(Order, cls).delete(orders)

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, orders):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('confirmed')
    def confirm(cls, orders):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('processing')
    def process(cls, orders):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('recieved')
    def recieve(cls, orders):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, orders):
        for order in orders:
            order.create_invoice()

    @classmethod
    @ModelView.button
    @Workflow.transition('refused')
    def refuse(cls, orders):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, orders):
        pass


class Invoice:
    __name__ = 'account.invoice'

    traffic_taxes_amount = fields.Function(fields.Numeric(
            'Traffic Taxes Total', digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits']),
        'get_amount')

    @classmethod
    def get_amount(cls, invoices, names):
        pool = Pool()
        Line = pool.get('account.invoice.line')
        res = super(Invoice, cls).get_amount(invoices, names)
        traffic_taxes_amount = {}.fromkeys([i.id for i in invoices],
            Decimal('0.0'))

        cursor = Transaction().cursor
        in_max = cursor.IN_MAX
        line = Line.__table__()
        for i in range(0, len(invoices), in_max):
            sub_ids = [i.id for i in invoices[i:i + in_max]]
            red_sql = reduce_ids(line.invoice, sub_ids)
            cursor.execute(*line.select(line.invoice,
                    Coalesce(Sum(line.traffic_taxes), 0),
                    where=red_sql,
                    group_by=line.invoice))
            for invoice, amount in cursor.fetchall():
                # SQLite uses float for SUM
                if not isinstance(amount, Decimal):
                    amount = Decimal(str(amount))
                traffic_taxes_amount[invoice] = amount

        if 'total_amount' in names:
            for invoice, value in traffic_taxes_amount.iteritems():
                res['total_amount'][invoice] += value
        if 'traffic_taxes_amount' in names:
            res['traffic_taxes_amount'] = traffic_taxes_amount
        return res


class InvoiceLine:
    __name__ = 'account.invoice.line'

    traffic_taxes = fields.Numeric('Traffic Taxes',
        digits=(16, Eval('_parent_invoice', {}).get('currency_digits',
                Eval('currency_digits', 2))),
        states={
            'invisible': ~Eval('type').in_(['line']),
            },
        depends=['type', 'currency_digits'])

    @classmethod
    def _get_origin(cls):
        models = super(InvoiceLine, cls)._get_origin()
        models.append('truck.order')
        return models
