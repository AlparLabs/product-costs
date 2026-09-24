from __future__ import annotations

from odoo.tests import Form, tagged

from .common import ReplenishmentCommon


@tagged('post_install', '-at_install')
class TestRuleByPartner(ReplenishmentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Rule = cls.env['product.replenishment_cost.rule']
        cls.rule_10 = Rule.create({
            'name': 'Bonif 10', 'item_ids': [(0, 0, {'name': 'b1', 'percentage_amount': -10.0})],
        })
        cls.rule_cascade = Rule.create({
            'name': '10+5+3',
            'item_ids': [
                (0, 0, {'name': 'b1', 'sequence': 1, 'percentage_amount': -10.0}),
                (0, 0, {'name': 'b2', 'sequence': 2, 'percentage_amount': -5.0}),
                (0, 0, {'name': 'b3', 'sequence': 3, 'percentage_amount': -3.0}),
            ],
        })

    def test_seller_inherits_partner_rule(self):
        self.vendor.replenishment_cost_rule_id = self.rule_cascade
        seller = self._seller(1000.0, self.main_company)
        self.assertEqual(seller.replenishment_cost_rule_id, self.rule_cascade)
        self.assertAlmostEqual(seller.net_price, 829.35, places=2)

    def test_contact_uses_commercial_partner_rule(self):
        self.vendor.replenishment_cost_rule_id = self.rule_10
        contact = self.env['res.partner'].create({
            'name': 'Vendedor', 'parent_id': self.vendor.id,
        })
        seller = self._seller(1000.0, self.main_company, partner=contact)
        self.assertEqual(seller.replenishment_cost_rule_id, self.rule_10)

    def test_partner_change_propagates(self):
        self.vendor.replenishment_cost_rule_id = self.rule_10
        seller = self._seller(1000.0, self.main_company)
        self.vendor.replenishment_cost_rule_id = self.rule_cascade
        self.assertEqual(seller.replenishment_cost_rule_id, self.rule_cascade)

    def test_own_rule_kept(self):
        self.vendor.replenishment_cost_rule_id = self.rule_10
        seller = self._seller(1000.0, self.main_company, use_own_rule=True,
                              replenishment_cost_rule_id=self.rule_cascade.id)
        self.vendor.replenishment_cost_rule_id = False
        self.assertEqual(seller.replenishment_cost_rule_id, self.rule_cascade)

    def test_editing_rule_in_form_marks_own(self):
        self.vendor.replenishment_cost_rule_id = self.rule_10
        seller = self._seller(1000.0, self.main_company)
        with Form(seller) as form:
            form.replenishment_cost_rule_id = self.rule_cascade
        self.assertTrue(seller.use_own_rule)
        self.vendor.replenishment_cost_rule_id = False
        self.assertEqual(seller.replenishment_cost_rule_id, self.rule_cascade)
