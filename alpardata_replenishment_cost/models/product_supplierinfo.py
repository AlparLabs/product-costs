from __future__ import annotations

from odoo import api, fields, models

from .company_hierarchy import company_ranks, seller_rank


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    use_own_rule = fields.Boolean(
        string='Regla propia',
        help='Si está tildado, la ficha conserva su regla aunque cambie la del proveedor.',
    )
    replenishment_cost_rule_id = fields.Many2one(
        compute='_compute_replenishment_cost_rule_id',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('partner_id.commercial_partner_id.replenishment_cost_rule_id', 'use_own_rule')
    def _compute_replenishment_cost_rule_id(self) -> None:
        for rec in self:
            if not rec.use_own_rule:
                rec.replenishment_cost_rule_id = (
                    rec.partner_id.commercial_partner_id.replenishment_cost_rule_id
                )

    @api.onchange('replenishment_cost_rule_id')
    def _onchange_replenishment_cost_rule_id_own(self) -> None:
        partner_rule = self.partner_id.commercial_partner_id.replenishment_cost_rule_id
        if self.replenishment_cost_rule_id != partner_rule:
            self.use_own_rule = True

    def _get_filtered_supplier(self, company_id, product_id, params=False):
        """Core: sólo empresa exacta o global. Acá: también las matrices de la
        empresa, y para cada proveedor sólo el nivel de empresa más específico.

        `product_id` falso significa "cualquier variante" (lo usa el cálculo del
        costo a nivel plantilla)."""
        ranks = company_ranks(company_id)
        candidates = self.filtered(
            lambda s: (not s.company_id or s.company_id.id in ranks)
            and s.partner_id.sudo().active
            and (not s.product_id or not product_id or s.product_id == product_id)
        )
        best: dict[int, int] = {}
        for seller in candidates:
            rank = seller_rank(seller, ranks)
            best[seller.partner_id.id] = min(best.get(seller.partner_id.id, rank), rank)
        return candidates.filtered(
            lambda s: seller_rank(s, ranks) == best[s.partner_id.id]
        )
