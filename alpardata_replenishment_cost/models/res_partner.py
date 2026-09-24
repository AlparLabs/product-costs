from __future__ import annotations

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    replenishment_cost_rule_id = fields.Many2one(
        'product.replenishment_cost.rule',
        string='Regla de costo',
        help='Regla de bonificaciones y recargos que heredan las fichas de este '
             'proveedor, salvo las que tengan regla propia.',
    )
