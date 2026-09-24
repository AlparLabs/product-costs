from __future__ import annotations

from odoo import models

from .company_hierarchy import company_ranks, seller_rank


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

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
