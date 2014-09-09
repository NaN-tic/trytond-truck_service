======================
Truck Service Scenario
======================

Imports::
    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import config, Model, Wizard
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install account_invoice::

    >>> Module = Model.get('ir.module.module')
    >>> module, = Module.find([('name', '=', 'truck_service')])
    >>> Module.install([module.id], config.context)
    >>> Wizard('ir.module.module.install_upgrade').execute('upgrade')

Create company::

    >>> Currency = Model.get('currency.currency')
    >>> CurrencyRate = Model.get('currency.currency.rate')
    >>> currencies = Currency.find([('code', '=', 'USD')])
    >>> if not currencies:
    ...     currency = Currency(name='US Dollar', symbol=u'$', code='USD',
    ...         rounding=Decimal('0.01'), mon_grouping='[]',
    ...         mon_decimal_point='.')
    ...     currency.save()
    ...     CurrencyRate(date=today + relativedelta(month=1, day=1),
    ...         rate=Decimal('1.0'), currency=currency).save()
    ... else:
    ...     currency, = currencies
    >>> Company = Model.get('company.company')
    >>> Party = Model.get('party.party')
    >>> company_config = Wizard('company.company.config')
    >>> company_config.execute('company')
    >>> company = company_config.form
    >>> party = Party(name='Dunder Mifflin')
    >>> party.save()
    >>> company.party = party
    >>> company.currency = currency
    >>> company_config.execute('add')
    >>> company, = Company.find([])

Reload the context::

    >>> User = Model.get('res.user')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> FiscalYear = Model.get('account.fiscalyear')
    >>> Sequence = Model.get('ir.sequence')
    >>> SequenceStrict = Model.get('ir.sequence.strict')
    >>> fiscalyear = FiscalYear(name=str(today.year))
    >>> fiscalyear.start_date = today + relativedelta(month=1, day=1)
    >>> fiscalyear.end_date = today + relativedelta(month=12, day=31)
    >>> fiscalyear.company = company
    >>> post_move_seq = Sequence(name=str(today.year), code='account.move',
    ...     company=company)
    >>> post_move_seq.save()
    >>> fiscalyear.post_move_sequence = post_move_seq
    >>> invoice_seq = SequenceStrict(name=str(today.year),
    ...     code='account.invoice', company=company)
    >>> invoice_seq.save()
    >>> fiscalyear.out_invoice_sequence = invoice_seq
    >>> fiscalyear.in_invoice_sequence = invoice_seq
    >>> fiscalyear.out_credit_note_sequence = invoice_seq
    >>> fiscalyear.in_credit_note_sequence = invoice_seq
    >>> fiscalyear.save()
    >>> FiscalYear.create_period([fiscalyear.id], config.context)

Create chart of accounts::

    >>> AccountTemplate = Model.get('account.account.template')
    >>> Account = Model.get('account.account')
    >>> account_template, = AccountTemplate.find([('parent', '=', None)])
    >>> create_chart = Wizard('account.create_chart')
    >>> create_chart.execute('account')
    >>> create_chart.form.account_template = account_template
    >>> create_chart.form.company = company
    >>> create_chart.execute('create_account')
    >>> receivable, = Account.find([
    ...         ('kind', '=', 'receivable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> payable, = Account.find([
    ...         ('kind', '=', 'payable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> revenue, = Account.find([
    ...         ('kind', '=', 'revenue'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> expense, = Account.find([
    ...         ('kind', '=', 'expense'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> account_tax, = Account.find([
    ...         ('kind', '=', 'other'),
    ...         ('company', '=', company.id),
    ...         ('name', '=', 'Main Tax'),
    ...         ])
    >>> create_chart.form.account_receivable = receivable
    >>> create_chart.form.account_payable = payable
    >>> create_chart.execute('create_properties')

Create tax::

    >>> TaxCode = Model.get('account.tax.code')
    >>> Tax = Model.get('account.tax')
    >>> tax = Tax()
    >>> tax.name = 'Tax'
    >>> tax.description = 'Tax'
    >>> tax.type = 'percentage'
    >>> tax.rate = Decimal('.10')
    >>> tax.invoice_account = account_tax
    >>> tax.credit_note_account = account_tax
    >>> invoice_base_code = TaxCode(name='invoice base')
    >>> invoice_base_code.save()
    >>> tax.invoice_base_code = invoice_base_code
    >>> invoice_tax_code = TaxCode(name='invoice tax')
    >>> invoice_tax_code.save()
    >>> tax.invoice_tax_code = invoice_tax_code
    >>> credit_note_base_code = TaxCode(name='credit note base')
    >>> credit_note_base_code.save()
    >>> tax.credit_note_base_code = credit_note_base_code
    >>> credit_note_tax_code = TaxCode(name='credit note tax')
    >>> credit_note_tax_code.save()
    >>> tax.credit_note_tax_code = credit_note_tax_code
    >>> tax.save()

Create Employee::

    >>> Employee = Model.get('company.employee')
    >>> party = Party(name='Employee')
    >>> party.save()
    >>> employee = Employee()
    >>> employee.party = party
    >>> employee.company = company
    >>> employee.save()
    >>> user, = User.find([])
    >>> user.employees.append(employee)
    >>> user.employee = employee
    >>> user.save()
    >>> config._context = User.get_preferences(True, config.context)

Create party::

    >>> Party = Model.get('party.party')
    >>> party = Party(name='Party')
    >>> address = party.addresses.new(invoice=True, sequence=10)
    >>> address = party.addresses.new(invoice=True, sequence=20)
    >>> party.save()
    >>> party.reload()
    >>> invoice_address, alternate_address, _ = party.addresses

Create a project for the party::

    >>> project = party.projects.new()
    >>> project.name = 'Project'
    >>> project.invoice_address = alternate_address
    >>> party.save()
    >>> party.reload()
    >>> project, = party.projects


Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'assets'
    >>> template.list_price = Decimal('10')
    >>> template.cost_price = Decimal('5')
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.customer_taxes.append(tax)
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> PaymentTermLine = Model.get('account.invoice.payment_term.line')
    >>> payment_term = PaymentTerm(name='Term')
    >>> payment_term_line = PaymentTermLine(type='percent', days=20,
    ...     percentage=Decimal(50))
    >>> payment_term.lines.append(payment_term_line)
    >>> payment_term_line = PaymentTermLine(type='remainder', days=40)
    >>> payment_term.lines.append(payment_term_line)
    >>> payment_term.save()

Create a vehicle::

    >>> Asset = Model.get('asset')
    >>> Vehicle = Model.get('asset.vehicle')
    >>> asset = Asset()
    >>> asset.product = product
    >>> asset.name = 'Vehicle'
    >>> asset.save()
    >>> vehicle = Vehicle()
    >>> vehicle.asset = asset
    >>> vehicle.driver = employee
    >>> vehicle.save()

Configure sequences::

    >>> Sequence = Model.get('ir.sequence')
    >>> Config = Model.get('truck.configuration')
    >>> config = Config(1)
    >>> order_sequence, = Sequence.find([('code', '=', 'truck.order')])
    >>> config.order_sequence = order_sequence
    >>> config.save()

Create a truck order::

    >>> Order = Model.get('truck.order')
    >>> order = Order()
    >>> order.order_date = today
    >>> order.party = party
    >>> order.invoice_address == invoice_address
    True
    >>> order.project = project
    >>> order.invoice_address == alternate_address
    True
    >>> order.notes = 'Notes'
    >>> order.vehicle = vehicle
    >>> order.unit_price
    Decimal('10')
    >>> order.tax == tax
    True
    >>> order.quantity = 2.0
    >>> order.save()
    >>> order.reload()

Check amounts::

    >>> order.reload()
    >>> order.untaxed_amount
    Decimal('20.00')
    >>> order.tax_amount
    Decimal('2.00')
    >>> order.total_amount
    Decimal('22.00')
    >>> order.various = Decimal('10.0')
    >>> order.save()
    >>> order.reload()
    >>> order.untaxed_amount
    Decimal('30.00')
    >>> order.tax_amount
    Decimal('3.00')
    >>> order.total_amount
    Decimal('33.00')
    >>> order.discount = Decimal('50.0')
    >>> order.traffic_taxes = Decimal('2.00')
    >>> order.save()
    >>> order.reload()
    >>> order.untaxed_amount
    Decimal('15.00')
    >>> order.tax_amount
    Decimal('1.50')
    >>> order.total_amount
    Decimal('18.50')

Create an invoice::

    >>> order.click('confirm')
    >>> order.start_time = datetime.datetime.now()
    >>> order.click('process')
    >>> order.end_time = datetime.datetime.now()
    >>> order.click('recieve')
    >>> order.click('done')
    >>> invoice, = order.invoices
    >>> invoice.untaxed_amount
    Decimal('15.00')
    >>> invoice.tax_amount
    Decimal('1.50')
    >>> invoice.traffic_taxes_amount
    Decimal('2.0')
    >>> invoice.total_amount
    Decimal('18.50')
    >>> line, = invoice.lines
    >>> line.gross_unit_price
    Decimal('30.0000')
    >>> line.discount
    Decimal('0.500')
    >>> line.traffic_taxes
    Decimal('2.00')
    >>> line.unit_price
    Decimal('15.00000000')
    >>> line.quantity
    1.0
    >>> line.product == product
    True
    >>> line.taxes == [tax]
    True
    >>> line.description == order.notes
    True
