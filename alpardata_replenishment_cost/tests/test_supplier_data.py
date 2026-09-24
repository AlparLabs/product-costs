from __future__ import annotations

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ReplenishmentCommon


@tagged('post_install', '-at_install')
class TestSupplierData(ReplenishmentCommon):

    def _cost(self, company=None):
        return self.template.with_company(company or self.main_company).replenishment_cost

    def test_future_seller_ignored(self):
        today = fields.Date.today()
        self._seller(100.0, self.main_company)
        self._seller(150.0, self.main_company, partner=self.vendor_b, sequence=0,
                     date_start=today + timedelta(days=5))
        self.assertEqual(self._cost(), 100.0)

    def test_expired_seller_ignored(self):
        today = fields.Date.today()
        self._seller(100.0, self.main_company, sequence=5)
        self._seller(150.0, self.main_company, partner=self.vendor_b, sequence=0,
                     date_end=today - timedelta(days=1))
        self.assertEqual(self._cost(), 100.0)

    def test_most_specific_company_first(self):
        self._seller(100.0, self.main_company, sequence=1)
        self._seller(120.0, self.branch, partner=self.vendor_b, sequence=5)
        self.assertEqual(self._cost(self.branch), 120.0)

    def test_sequence_then_latest_start(self):
        today = fields.Date.today()
        self._seller(100.0, self.main_company, sequence=10,
                     date_start=today - timedelta(days=30))
        self._seller(110.0, self.main_company, partner=self.vendor_b, sequence=10,
                     date_start=today - timedelta(days=2))
        self.assertEqual(self._cost(), 110.0)

    def test_zero_price_ignored(self):
        self._seller(0.0, self.main_company, sequence=0)
        self._seller(90.0, self.main_company, partner=self.vendor_b, sequence=5)
        self.assertEqual(self._cost(), 90.0)

    def test_uom_pack_converted(self):
        uom_unit = self.env.ref('uom.product_uom_unit')
        pack = self.env['uom.uom'].create({
            'name': 'Pack x24 Test', 'relative_factor': 24.0,
            'relative_uom_id': uom_unit.id,
        })
        self._seller(2400.0, self.main_company, product_uom_id=pack.id)
        self.assertEqual(self._cost(), 100.0)

    def test_branch_uses_main_company_list(self):
        self._seller(100.0, self.main_company)
        self.assertEqual(self._cost(self.branch), 100.0)

    def test_last_supplier_price(self):
        self.template.replenishment_cost_type = 'last_supplier_price'
        old = self._seller(100.0, self.main_company, sequence=1)
        new = self._seller(130.0, self.main_company, partner=self.vendor_b, sequence=9)
        old.last_date_price_updated = fields.Datetime.now() - timedelta(days=3)
        new.last_date_price_updated = fields.Datetime.now()
        self.assertEqual(self._cost(), 130.0)
