from __future__ import annotations

from datetime import datetime

from odoo import api, fields, models

from .company_hierarchy import company_ranks, seller_rank


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    use_own_margin = fields.Boolean(
        string='Margen propio',
        help='Si está tildado, el producto conserva su margen aunque cambie el de la categoría.',
    )
    sale_margin = fields.Float(
        compute='_compute_sale_margin',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('categ_id.sale_margin', 'use_own_margin')
    def _compute_sale_margin(self) -> None:
        for rec in self:
            if not rec.use_own_margin:
                rec.sale_margin = rec.categ_id.sale_margin
            else:
                rec.sale_margin = rec.sale_margin

    @api.onchange('sale_margin')
    def _onchange_sale_margin_own(self) -> None:
        if self.sale_margin != self.categ_id.sale_margin:
            self.use_own_margin = True

    @api.depends_context('company')
    @api.depends(
        'seller_ids.net_price', 'seller_ids.currency_id', 'seller_ids.company_id',
        'seller_ids.date_start', 'seller_ids.date_end', 'seller_ids.sequence',
        'seller_ids.product_uom_id', 'seller_ids.last_date_price_updated',
        'replenishment_cost_type', 'uom_id',
    )
    def _compute_supplier_data(self):
        """Reemplaza el de Adhoc: sólo fichas vigentes hoy, jerarquía de empresas,
        orden como el módulo anterior (empresa, secuencia, inicio más reciente, id)
        y precio convertido a la unidad del producto."""
        today = fields.Date.context_today(self)
        company = self.env.company
        ranks = company_ranks(company)
        empty_currency = self.env['res.currency']
        for rec in self:
            sellers = rec.seller_ids._get_filtered_supplier(company, False).filtered(
                lambda s: (not s.date_start or s.date_start <= today)
                and (not s.date_end or s.date_end >= today)
                and s.net_price > 0
            )
            if rec.replenishment_cost_type == 'last_supplier_price':
                sellers = sellers.sorted(
                    key=lambda s: s.last_date_price_updated or datetime.min, reverse=True,
                )
            else:
                sellers = sellers.sorted(key=lambda s: (
                    seller_rank(s, ranks),
                    s.sequence,
                    -(s.date_start.toordinal() if s.date_start else 0),
                    s.id,
                ))
            seller = sellers[:1]
            price = seller.net_price if seller else 0.0
            if seller and seller.product_uom_id and rec.uom_id and seller.product_uom_id != rec.uom_id:
                price = seller.product_uom_id._compute_price(price, rec.uom_id)
            rec.update({
                'supplier_price': price,
                'supplier_currency_id': seller.currency_id if seller else empty_currency,
            })
