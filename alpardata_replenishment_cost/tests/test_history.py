from __future__ import annotations

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ReplenishmentCommon


@tagged('post_install', '-at_install')
class TestPriceHistory(ReplenishmentCommon):

    def _history(self):
        return self.env['product.supplierinfo.price.history'].search([
            ('product_tmpl_id', '=', self.template.id),
        ], order='id asc')

    def test_create_logs_with_previous_price(self):
        self._seller(100.0, self.main_company)
        self._seller(120.0, self.main_company,
                     date_start=fields.Date.today())
        last = self._history()[-1]
        self.assertEqual(last.old_price, 100.0)
        self.assertEqual(last.new_price, 120.0)

    def test_price_change_logs_reason(self):
        seller = self._seller(100.0, self.main_company)
        seller.with_context(_change_reason='Lista marzo').price = 110.0
        last = self._history()[-1]
        self.assertEqual((last.old_price, last.new_price), (100.0, 110.0))
        self.assertEqual(last.change_reason, 'Lista marzo')
        self.assertEqual(last.changed_by, self.env.user)

    def test_rule_change_logs(self):
        rule = self.env['product.replenishment_cost.rule'].create({'name': 'R'})
        seller = self._seller(100.0, self.main_company)
        seller.write({'use_own_rule': True, 'replenishment_cost_rule_id': rule.id})
        self.assertEqual(self._history()[-1].new_rule_id, rule)

    def test_same_price_not_logged(self):
        seller = self._seller(100.0, self.main_company)
        count = len(self._history())
        seller.price = 100.0
        self.assertEqual(len(self._history()), count)

    def test_new_dated_seller_closes_previous(self):
        today = fields.Date.today()
        old = self._seller(100.0, self.main_company)
        self._seller(120.0, self.main_company, date_start=today)
        self.assertEqual(old.date_end, today - timedelta(days=1))

    def test_future_seller_not_closed(self):
        today = fields.Date.today()
        future = self._seller(150.0, self.main_company, date_start=today + timedelta(days=10))
        self._seller(120.0, self.main_company, date_start=today)
        self.assertFalse(future.date_end)

    def test_other_company_not_closed(self):
        today = fields.Date.today()
        other = self._seller(100.0, self.branch)
        self._seller(120.0, self.main_company, date_start=today)
        self.assertFalse(other.date_end)
