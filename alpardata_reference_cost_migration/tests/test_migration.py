from __future__ import annotations

import base64

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.alpardata_reference_cost_migration import migration


@tagged('post_install', '-at_install')
class TestMigration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vendor = cls.env['res.partner'].create({'name': 'Proveedor Migración'})
        cls.template = cls.env['product.template'].create({'name': 'Producto Migración'})
        cls.seller = cls.env['product.supplierinfo'].create({
            'partner_id': cls.vendor.id,
            'product_tmpl_id': cls.template.id,
            'company_id': cls.company.id,
            'price': 0.0,
            'reference_cost': 500.0,
        })
        cls.seller.with_context(_change_reason='Lista vieja').reference_cost = 550.0

    def test_check_pricelist_bases_aborts(self):
        self.env['product.pricelist'].create({
            'name': 'Lista referencia',
            'item_ids': [(0, 0, {
                'applied_on': '3_global', 'compute_price': 'formula', 'base': 'reference_cost',
            })],
        })
        with self.assertRaises(UserError):
            migration.check_pricelist_bases(self.env)

    def test_copy_prices_without_history(self):
        history = self.env['product.supplierinfo.price.history']
        before = history.search_count([])
        migration.copy_prices(self.env)
        self.seller.invalidate_recordset()
        self.assertEqual(self.seller.price, 550.0)
        self.assertEqual(history.search_count([]), before)

    def test_copy_history(self):
        migration.copy_history(self.env)
        rows = self.env['product.supplierinfo.price.history'].search([
            ('supplierinfo_id', '=', self.seller.id),
        ])
        self.assertIn((500.0, 550.0), [(r.old_price, r.new_price) for r in rows])
        self.assertIn('Lista vieja', rows.mapped('change_reason'))

    def test_set_cost_types(self):
        migration.copy_prices(self.env)
        migration.set_cost_types(self.env)
        self.template.invalidate_recordset()
        self.assertEqual(self.template.replenishment_cost_type, 'supplier_price')

    def test_verification_empty_after_migration(self):
        snapshot = migration.snapshot_costs(self.env)
        migration.copy_prices(self.env)
        migration.set_cost_types(self.env)
        rows = migration.verify(self.env, snapshot)
        self.assertEqual(rows, [])

    def test_verification_reports_difference(self):
        snapshot = migration.snapshot_costs(self.env)
        migration.copy_prices(self.env)
        migration.set_cost_types(self.env)
        self.seller.price = 999.0
        rows = migration.verify(self.env, snapshot)
        self.assertTrue(any(r['product_tmpl_id'] == self.template.id for r in rows))
        attachment = migration.write_report(self.env, rows)
        self.assertIn(b'999', base64.b64decode(attachment.datas))
