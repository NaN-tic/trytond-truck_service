# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval

__all__ = ['Party', 'Project']
__metaclass__ = PoolMeta


class Party:
    __name__ = 'party.party'

    projects = fields.One2Many('party.project', 'party', 'Projects')


class Project(ModelSQL, ModelView):
    'Party Project'
    __name__ = 'party.project'
    party = fields.Many2One('party.party', 'Party', required=True,
        ondelete='CASCADE')
    name = fields.Char('Name', required=True)
    invoice_address = fields.Many2One('party.address', 'Invoice Address',
        domain=[
            ('party', '=', Eval('party')),
            ],
        depends=['party'])
