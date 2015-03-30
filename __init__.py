# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .configuration import *
from .party import *
from .truck import *


def register():
    Pool.register(
        Configuration,
        ConfigurationCompany,
        Party,
        Project,
        Order,
        Invoice,
        InvoiceLine,
        ExistentInvoice,
        module='truck_service', type_='model')
    Pool.register(
        OrderInvoice,
        UpdateOrderInvoice,
        module='truck_service', type_='wizard')
