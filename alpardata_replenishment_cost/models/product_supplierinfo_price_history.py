from __future__ import annotations

from odoo import api, fields, models


class ProductSupplierinfoPriceHistory(models.Model):
    _name = 'product.supplierinfo.price.history'
    _description = 'Historial de precios de proveedor'
    _order = 'change_date desc, id desc'
    _rec_name = 'partner_id'

    supplierinfo_id = fields.Many2one(
        'product.supplierinfo', string='Ficha de proveedor', ondelete='set null', index=True,
    )
    product_tmpl_id = fields.Many2one(
        'product.template', string='Producto', ondelete='cascade', index=True,
    )
    partner_id = fields.Many2one('res.partner', string='Proveedor', index=True)
    company_id = fields.Many2one('res.company', string='Empresa', index=True)
    currency_id = fields.Many2one('res.currency', string='Moneda')
    old_price = fields.Float(string='Precio anterior', digits='Product Price')
    new_price = fields.Float(string='Precio nuevo', digits='Product Price')
    variation_pct = fields.Float(
        string='Variación (%)', compute='_compute_variation_pct', store=True, digits=(16, 2),
    )
    old_rule_id = fields.Many2one('product.replenishment_cost.rule', string='Regla anterior')
    new_rule_id = fields.Many2one('product.replenishment_cost.rule', string='Regla nueva')
    change_date = fields.Datetime(string='Fecha', default=fields.Datetime.now, index=True)
    changed_by = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user)
    change_reason = fields.Char(string='Motivo')

    @api.depends('old_price', 'new_price')
    def _compute_variation_pct(self) -> None:
        for rec in self:
            rec.variation_pct = (
                (rec.new_price / rec.old_price - 1) * 100 if rec.old_price else 0.0
            )
