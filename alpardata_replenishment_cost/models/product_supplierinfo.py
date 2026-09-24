from __future__ import annotations

from datetime import timedelta

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
    price_history_count = fields.Integer(compute='_compute_price_history_count')

    @api.depends('partner_id.commercial_partner_id.replenishment_cost_rule_id', 'use_own_rule')
    def _compute_replenishment_cost_rule_id(self) -> None:
        for rec in self:
            if not rec.use_own_rule:
                rec.replenishment_cost_rule_id = (
                    rec.partner_id.commercial_partner_id.replenishment_cost_rule_id
                )
            else:
                rec.replenishment_cost_rule_id = rec.replenishment_cost_rule_id

    @api.onchange('replenishment_cost_rule_id')
    def _onchange_replenishment_cost_rule_id_own(self) -> None:
        partner_rule = self.partner_id.commercial_partner_id.replenishment_cost_rule_id
        if self.replenishment_cost_rule_id != partner_rule:
            self.use_own_rule = True

    def _compute_price_history_count(self) -> None:
        data = self.env['product.supplierinfo.price.history']._read_group(
            [('supplierinfo_id', 'in', self.ids)], ['supplierinfo_id'], ['__count'],
        )
        counts = {seller.id: count for seller, count in data}
        for rec in self:
            rec.price_history_count = counts.get(rec.id, 0)

    def _history_vals(self, old_price, new_price, old_rule, new_rule) -> dict:
        self.ensure_one()
        return {
            'supplierinfo_id': self.id,
            'product_tmpl_id': self.product_tmpl_id.id,
            'partner_id': self.partner_id.id,
            'company_id': (self.company_id or self.env.company).id,
            'currency_id': self.currency_id.id,
            'old_price': old_price,
            'new_price': new_price,
            'old_rule_id': old_rule.id if old_rule else False,
            'new_rule_id': new_rule.id if new_rule else False,
            'change_reason': self.env.context.get('_change_reason', 'Actualización manual'),
        }

    def _same_slot_domain(self) -> list:
        """Fichas del mismo proveedor, producto y empresa (excluyendo self)."""
        self.ensure_one()
        return [
            ('id', '!=', self.id),
            ('partner_id', '=', self.partner_id.id),
            ('product_tmpl_id', '=', self.product_tmpl_id.id),
            ('company_id', '=', self.company_id.id if self.company_id else False),
        ]

    def _previous_active(self):
        """Ficha vigente hoy del mismo proveedor, producto y empresa."""
        today = fields.Date.context_today(self)
        return self.sudo().search(self._same_slot_domain() + [
            '|', ('date_start', '=', False), ('date_start', '<=', today),
            '|', ('date_end', '=', False), ('date_end', '>=', today),
        ], order='sequence asc, id desc', limit=1)

    def _close_previous_records(self) -> None:
        """Al crear una ficha con fecha de inicio, cierra las anteriores del mismo
        proveedor, producto y empresa vigentes a esa fecha. No toca las que
        empiezan después."""
        self.ensure_one()
        if not self.date_start:
            return
        previous = self.sudo().search(self._same_slot_domain() + [
            '|', ('date_end', '=', False), ('date_end', '>=', self.date_start),
            '|', ('date_start', '=', False), ('date_start', '<', self.date_start),
        ])
        previous.write({'date_end': self.date_start - timedelta(days=1)})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        History = self.env['product.supplierinfo.price.history'].sudo()
        history_vals = []
        for rec in records:
            if not rec.product_tmpl_id:
                continue
            previous = rec._previous_active()
            history_vals.append(rec._history_vals(
                previous.price if previous else 0.0, rec.price,
                previous.replenishment_cost_rule_id if previous else False,
                rec.replenishment_cost_rule_id,
            ))
            rec._close_previous_records()
        if history_vals:
            History.create(history_vals)
        return records

    def write(self, vals):
        tracked = {'price', 'replenishment_cost_rule_id'} & set(vals)
        before = {}
        if tracked:
            before = {rec.id: (rec.price, rec.replenishment_cost_rule_id) for rec in self}
        res = super().write(vals)
        if tracked:
            history_vals = []
            for rec in self.filtered('product_tmpl_id'):
                old_price, old_rule = before[rec.id]
                if old_price != rec.price or old_rule != rec.replenishment_cost_rule_id:
                    history_vals.append(rec._history_vals(
                        old_price, rec.price, old_rule, rec.replenishment_cost_rule_id,
                    ))
            if history_vals:
                self.env['product.supplierinfo.price.history'].sudo().create(history_vals)
        return res

    def action_view_price_history(self) -> dict:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Historial de precios — {self.partner_id.name}',
            'res_model': 'product.supplierinfo.price.history',
            'view_mode': 'list',
            'domain': [('supplierinfo_id', '=', self.id)],
        }

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
