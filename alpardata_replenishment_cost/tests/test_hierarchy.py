from __future__ import annotations

from odoo.tests import tagged

from .common import ReplenishmentCommon


@tagged('post_install', '-at_install')
class TestSupplierHierarchy(ReplenishmentCommon):

    def _filtered(self, company):
        return self.template.seller_ids._get_filtered_supplier(company, self.product)

    def test_branch_sees_main_company(self):
        seller = self._seller(100.0, self.main_company)
        self.assertEqual(self._filtered(self.branch), seller)

    def test_branch_own_seller_wins_for_same_vendor(self):
        self._seller(100.0, self.main_company)
        own = self._seller(120.0, self.branch)
        self.assertEqual(self._filtered(self.branch), own)

    def test_other_vendor_of_main_company_kept(self):
        own = self._seller(120.0, self.branch)
        other = self._seller(90.0, self.main_company, partner=self.vendor_b)
        self.assertEqual(self._filtered(self.branch), own | other)

    def test_global_kept_when_no_specific(self):
        seller = self._seller(80.0)
        self.assertEqual(self._filtered(self.branch), seller)

    def test_independent_does_not_see_other_company(self):
        self._seller(100.0, self.main_company)
        self.assertFalse(self._filtered(self.independent))

    def test_purchase_order_of_branch_uses_main_company_price(self):
        self._seller(100.0, self.main_company)
        po = self.env['purchase.order'].with_company(self.branch).create({
            'partner_id': self.vendor.id, 'company_id': self.branch.id,
        })
        line = self.env['purchase.order.line'].with_company(self.branch).create({
            'order_id': po.id, 'product_id': self.product.id, 'product_qty': 1.0,
        })
        self.assertEqual(line.price_unit, 100.0)
