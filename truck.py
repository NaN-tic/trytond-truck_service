# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
from sql.aggregate import Sum
from sql.conditionals import Coalesce
from sql import Cast, Literal
from sql.functions import Substring, Position

from trytond.pool import Pool, PoolMeta
from trytond.model import Workflow, ModelSQL, ModelView, fields
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.pyson import Eval, If, In
from trytond.tools import reduce_ids
from trytond.transaction import Transaction
from trytond.modules.jasper_reports.jasper import JasperReport

__all__ = ['Order', 'Invoice', 'InvoiceLine', 'OrderInvoice',
    'ExistentInvoice', 'UpdateOrderInvoice', 'OrderNoteReport']
__metaclass__ = PoolMeta


_STATES = {
    'readonly': Eval('state') != 'draft',
    }
_STATES_REQUIRED = {
    'readonly': ~Eval('state').in_(['draft']),
    'required': Eval('state').in_(['draft']),
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
            ('party', '=', Eval('party')),
            ('delivery', '=', True),
            ],
        states=_STATES, depends=_DEPENDS + ['party'])
    order_date = fields.Date('Order Date', required=True, states=_STATES,
        depends=_DEPENDS)
    start_time = fields.DateTime('Start Date')
    end_time = fields.DateTime('End Date')
    notes = fields.Text('Notes', required=True, states=_STATES,
        depends=_DEPENDS)
    vehicle = fields.Many2One('asset', 'Vehicle', required=True,
        domain=[
            ('type', '=', 'vehicle'),
            ],
        context={
            'type': 'vehicle',
            },
        states=_STATES, depends=_DEPENDS)
    product = fields.Many2One('product.product', 'Vehicle Type',
        states=_STATES, depends=_DEPENDS)
    driver = fields.Many2One('company.employee', 'Driver',
        states=_STATES, depends=_DEPENDS)
    payment_term = fields.Many2One('account.invoice.payment_term',
        'Payment Term', required=True, states=_STATES, depends=_DEPENDS)
    quantity = fields.Float('Quantity', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    unit_price = fields.Numeric('Unit Price', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    traffic_taxes = fields.Numeric('Traffic Taxes', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    discount = fields.Numeric('Discount', digits=(16, 4),
        states=_STATES, depends=_DEPENDS)
    tax = fields.Many2One('account.tax', 'Tax', ondelete='RESTRICT',
        domain=[
            ('parent', '=', None),
            ['OR',
                ('group', '=', None),
                ('group.kind', 'in', ['sale', 'both'])
                ],
            ],
        states=_STATES_REQUIRED, depends=_DEPENDS)
    untaxed_amount = fields.Function(fields.Numeric('Untaxed',
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits']),
        'get_amount')
    tax_amount = fields.Function(fields.Numeric('Tax', digits=(16,
                Eval('currency_digits', 2)), depends=['currency_digits']),
        'get_amount')
    total_amount = fields.Function(fields.Numeric('Total', digits=(16,
                Eval('currency_digits', 2)), depends=['currency_digits']),
        'get_amount')
    invoice_lines = fields.One2Many('account.invoice.line', 'origin',
        'Invoice Lines', readonly=True)
    invoices = fields.Function(fields.One2Many('account.invoice', None,
            'Invoices'),
        'get_invoices')
    invoiced = fields.Function(fields.Boolean('Invoiced'), 'check_invoiced',
        searcher='search_invoiced')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ], 'State', readonly=True)

    @classmethod
    def __setup__(cls):
        super(Order, cls).__setup__()
        cls._sql_constraints = [
            ('reference_uniq', 'UNIQUE(reference)',
                 'The References of the order must be unique.')]
        cls._order.insert(0, ('order_date', 'DESC'))
        cls._order.insert(1, ('id', 'DESC'))
        cls._error_messages.update({
                'delete_cancel': ('Truck Order "%s" must be cancelled before'
                    ' deletion.'),
                'no_sequence': ('There is no Truck Order sequence. Please '
                    'define one in configuration.'),
                'missing_account_revenue': ('Product "%(product)s" of vehicle'
                    ' %(vehicle)s misses a revenue account.'),
                'not_same_party': ('Trying to create an invoice with orders '
                    'from differnts parties.'),
                'not_done': ('The order %s could not be invoiced because are '
                    'not done.'),
                'order_invoiced': ('The order %s is already invoiced.'),
                })
        cls._transitions |= set((
                ('draft', 'done'),
                ('done', 'draft'),
                ))
        cls._buttons.update({
                'draft': {
                    'invisible': Eval('state') != 'done',
                    'icon': 'tryton-clear',
                    },
                'done': {
                    'invisible': Eval('state') != 'draft',
                    'icon': 'tryton-ok',
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
                # Delivery address may not exist
                delivery_address = self.party.address_get(type='delivery')
                if not delivery_address.delivery:
                    delivery_address = None
            except AttributeError:
                pass
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

    @fields.depends('vehicle', 'unit_price', 'quantity', 'discount', 'tax',
        'currency_digits', 'traffic_taxes')
    def on_change_vehicle(self):
        changes = {}
        if self.vehicle:
            if self.vehicle.product:
                product = self.vehicle.product
                changes['product'] = product.id
                changes['product.rec_name'] = product.rec_name
                changes['unit_price'] = product.list_price
                if product.customer_taxes:
                    changes['tax'] = product.customer_taxes[0].id
                    changes['tax.rec_name'] = (
                        product.customer_taxes[0].rec_name)
                amount = self.get_amount([self],
                    ['untaxed_amount', 'tax_amount', 'total_amount'])
                changes['untaxed_amount'] = amount['untaxed_amount'][self.id]
                changes['tax_amount'] = amount['tax_amount'][self.id]
                changes['total_amount'] = amount['total_amount'][self.id]
            if self.vehicle.driver:
                changes['driver'] = self.vehicle.driver.id
                changes['driver.rec_name'] = self.vehicle.driver.rec_name
        return changes

    @fields.depends('product', 'unit_price', 'quantity', 'discount', 'tax',
        'currency_digits', 'traffic_taxes')
    def on_change_product(self):
        changes = {}
        if self.product:
            changes['unit_price'] = self.product.list_price
            if self.product.customer_taxes:
                changes['tax'] = self.product.customer_taxes[0].id
                changes['tax.rec_name'] = (
                    self.product.customer_taxes[0].rec_name)
            amount = self.get_amount([self],
                ['untaxed_amount', 'tax_amount', 'total_amount'])
            changes['untaxed_amount'] = amount['untaxed_amount'][self.id]
            changes['tax_amount'] = amount['tax_amount'][self.id]
            changes['total_amount'] = amount['total_amount'][self.id]
        return changes

    @fields.depends('quantity', 'unit_price', 'quantity', 'discount', 'tax',
        'currency_digits', 'traffic_taxes')
    def on_change_quantity(self):
        changes = {}
        if self.quantity:
            amount = self.get_amount([self],
                ['untaxed_amount', 'tax_amount', 'total_amount'])
            changes['untaxed_amount'] = amount['untaxed_amount'][self.id]
            changes['tax_amount'] = amount['tax_amount'][self.id]
            changes['total_amount'] = amount['total_amount'][self.id]
        return changes

    @fields.depends('unit_price', 'unit_price', 'quantity', 'discount', 'tax',
        'currency_digits', 'traffic_taxes')
    def on_change_unit_price(self):
        changes = {}
        if self.quantity:
            amount = self.get_amount([self],
                ['untaxed_amount', 'tax_amount', 'total_amount'])
            changes['untaxed_amount'] = amount['untaxed_amount'][self.id]
            changes['tax_amount'] = amount['tax_amount'][self.id]
            changes['total_amount'] = amount['total_amount'][self.id]
        return changes

    @classmethod
    def get_amount(cls, orders, names):
        pool = Pool()
        Tax = pool.get('account.tax')
        untaxed_amount = {}.fromkeys([o.id for o in orders], Decimal('0.0'))
        tax_amount = {}.fromkeys([o.id for o in orders], Decimal('0.0'))
        total_amount = {}.fromkeys([o.id for o in orders], Decimal('0.0'))
        for order in orders:
            unit_price = order.unit_price or Decimal(0)
            gross = (Decimal(str(order.quantity or 0.0)) * unit_price)
            untaxed = gross - ((order.discount or Decimal(0.0)) * gross / 100)
            if order.tax:
                vals = Tax.compute([order.tax], untaxed, 1.0)
                if vals:
                    val, = vals
                else:
                    val = {'amount': Decimal('0.0')}
            else:
                val = {'amount': Decimal('0.0')}
            tax_amount[order.id] = Decimal(val['amount']).quantize(
                    Decimal(str(10 ** - (order.currency_digits or 0))))
            untaxed_amount[order.id] = Decimal(untaxed).quantize(
                    Decimal(str(10 ** - (order.currency_digits or 0))))
            total_amount[order.id] = Decimal(untaxed + val['amount'] + (
                    order.traffic_taxes or Decimal('0.0'))).quantize(
                        Decimal(str(10 ** - (order.currency_digits or 0))))

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
    def check_orders(cls, orders):
        # Check all orders are from the same party and done and not invoiced
        last_party = None
        for order in orders:
            if order.state != 'done':
                cls.raise_user_error('not_done', (order.rec_name,))
            if order.invoiced:
                cls.raise_user_error('order_invoiced', (order.rec_name,))
            party = order.party
            if last_party is None:
                last_party = party
            if party.id != last_party.id:
                cls.raise_user_error('not_same_party')

    @classmethod
    def get_invoices(cls, orders, name):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        lines = InvoiceLine.search([
                ('origin.id', 'in', [o.id for o in orders], 'truck.order'),
                ])

        result = {}
        for order in orders:
            result[order.id] = []
        for line in lines:
            order = line.origin.id
            invoice = line.invoice.id
            if invoice not in result[order]:
                result[order].append(invoice)
        return result

    @classmethod
    def check_invoiced(cls, orders, name):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        lines = InvoiceLine.search([
                ('origin.id', 'in', [o.id for o in orders], 'truck.order'),
                ])

        result = {}
        for order in orders:
            result[order.id] = False
        for line in lines:
            invoice = line.invoice.id
            if invoice:
                result[line.origin.id] = True
        return result

    @classmethod
    def search_invoiced(cls, name, clause):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')

        order = cls.__table__()
        invoice_line = InvoiceLine.__table__()

        query = order.join(invoice_line,
            condition=(order.id == Cast(Substring(invoice_line.origin,
                        Position(',', invoice_line.origin) + Literal(1)),
                    InvoiceLine.id.sql_type().base))).select(order.id)
        return [('id', 'in', query)]

    @classmethod
    def create_invoice_lines(cls, invoice, orders):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')

        with Transaction().set_user(0):
            invoice_line = InvoiceLine()

        for order in orders:
            invoice_line.type = 'line'
            invoice_line.description = order.notes or ''
            invoice_line.party = order.party
            invoice_line.quantity = 1.0
            unit_price = order.unit_price or Decimal(0)
            invoice_line.gross_unit_price = (Decimal(
                    str(order.quantity or 0.0)) * unit_price)
            invoice_line.discount = (
                (order.discount or Decimal(0.0)) * Decimal('.01'))
            invoice_line.unit_price = (
                invoice_line.update_prices()['unit_price'])
            invoice_line.traffic_taxes = order.traffic_taxes or Decimal(0.0)
            invoice_line.origin = order

            product = order.vehicle.product
            invoice_line.account = None
            if product:
                invoice_line.product = product
                invoice_line.unit = product.default_uom
                invoice_line.account = product.account_revenue_used
            if not invoice_line.account:
                order.raise_user_error('missing_account_revenue', {
                        'vehicle': order.vehicle.rec_name,
                        'product': product.rec_name if product else '',
                        })
            invoice_line.taxes = [order.tax]
            invoice.lines = ((list(invoice.lines)
                    if hasattr(invoice, 'lines') else [])
                + list([invoice_line]))
            invoice.save()

    @classmethod
    def create_invoice(cls, orders):
        'Return the invoice to create for the given order'
        pool = Pool()
        Journal = pool.get('account.journal')
        Invoice = pool.get('account.invoice')

        cls.check_orders(orders)

        with Transaction().set_user(0):
            invoice = Invoice()

        invoice.company = orders[0].company
        invoice.currency = orders[0].company.currency
        invoice.reference = orders[0].reference
        invoice.type = 'out_invoice'
        invoice.party = orders[0].party
        for key, value in invoice.on_change_party().iteritems():
            setattr(invoice, key, value)
        invoice.payment_term = orders[0].payment_term
        invoice.invoice_address = orders[0].invoice_address
        journals = Journal.search([
                ('type', '=', 'revenue'),
                ], limit=1)
        if journals:
            journal, = journals
            invoice.journal = journal

        cls.create_invoice_lines(invoice, orders)

        with Transaction().set_user(0, set_context=True):
            Invoice.update_taxes([invoice])

    @classmethod
    def update_invoice(cls, orders, invoice):
        'Add selected order to an existent invoice'
        pool = Pool()
        Invoice = pool.get('account.invoice')

        cls.create_invoice_lines(invoice, orders)

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
        for order in orders:
            if order.state != 'draft':
                cls.raise_user_error('delete_cancel', (order.rec_name,))
        super(Order, cls).delete(orders)

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, orders):
        for order in orders:
            if order.invoiced:
                cls.raise_user_error('order_invoiced', (order.rec_name,))


    @classmethod
    @ModelView.button
    @Workflow.transition('done')
    def done(cls, orders):
        pass


class OrderInvoice(Wizard):
    'Inovice Truck Order'
    __name__ = 'truck.order.invoice'

    start_state = 'invoice'
    invoice = StateTransition()

    def transition_invoice(self):
        pool = Pool()
        Order = pool.get('truck.order')
        orders = Order.browse(Transaction().context.get('active_ids'))
        Order.create_invoice(orders)
        return 'end'


class ExistentInvoice(ModelView):
    'Existent Invoice'
    __name__ = 'truck.order.invoice.existent'

    party = fields.Many2One('party.party', 'Party')
    invoice = fields.Many2One('account.invoice', 'Invoice', required=True,
        domain=[
            ('party', '=', Eval('party', None)),
            ('state', '=', 'draft'),
            ], depends=['party'])


class UpdateOrderInvoice(Wizard):
    'Update Inovice Truck Order'
    __name__ = 'truck.order.invoice.update'

    start = StateView('truck.order.invoice.existent',
        'truck_service.truck_order_invoice_existent_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Add', 'add', 'tryton-ok', default=True),
            ])
    add = StateTransition()

    def default_start(self, fields):
        pool = Pool()
        Order = pool.get('truck.order')
        Invoice = pool.get('account.invoice')
        orders = Order.browse(Transaction().context.get('active_ids'))

        Order.check_orders(orders)

        party = orders[0].party
        invoices = Invoice.search([
                ('party', '=', party.id),
                ('state', '=', 'draft'),
                ])

        return {
            'party': party and party.id or None,
            'invoice': invoices and invoices[0] and invoices[0].id or None,
            }

    def transition_add(self):
        Order = Pool().get('truck.order')
        orders = Transaction().context.get('active_ids')
        invoice = self.start.invoice
        Order.update_invoice(Order.browse(orders), invoice)
        return 'end'


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
                    Coalesce(Sum(line.traffic_taxes or Decimal(0.0)), 0),
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


class OrderNoteReport(JasperReport):
    __name__ = 'truck.order.note.jasper'
