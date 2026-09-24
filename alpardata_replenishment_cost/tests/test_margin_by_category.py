from __future__ import annotations

from odoo.tests import tagged

from .common import ReplenishmentCommon


@tagged('post_install', '-at_install')
class TestMarginByCategory(ReplenishmentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categ = cls.env['product.category'].create({
            'name': 'Almacén Test', 'sale_margin': 40.0,
        })

    def test_product_inherits_category_margin(self):
        template = self.env['product.template'].create({
            'name': 'Fideos', 'categ_id': self.categ.id,
        })
        self.assertEqual(template.sale_margin, 40.0)

    def test_category_change_propagates(self):
        template = self.env['product.template'].create({
            'name': 'Fideos', 'categ_id': self.categ.id,
        })
        self.categ.sale_margin = 35.0
        self.assertEqual(template.sale_margin, 35.0)

    def test_own_margin_kept(self):
        template = self.env['product.template'].create({
            'name': 'Fideos', 'categ_id': self.categ.id,
            'use_own_margin': True, 'sale_margin': 25.0,
        })
        self.categ.sale_margin = 50.0
        self.assertEqual(template.sale_margin, 25.0)

    def test_planned_price_by_margin(self):
        template = self.env['product.template'].with_company(self.main_company).create({
            'name': 'Fideos', 'categ_id': self.categ.id,
            'replenishment_cost_type': 'supplier_price',
            'list_price_type': 'by_margin',
            'taxes_id': [(5, 0, 0)],
        })
        self.env['product.supplierinfo'].create({
            'partner_id': self.vendor.id, 'product_tmpl_id': template.id,
            'company_id': False, 'price': 1000.0,
        })
        self.assertAlmostEqual(template.computed_list_price, 1400.0, places=2)
