from __future__ import annotations

from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    sale_margin = fields.Float(
        string='Margen de venta (%)',
        digits='Discount',
        help='Margen del precio planificado que heredan los productos de esta '
             'categoría, salvo los que tengan margen propio.',
    )
