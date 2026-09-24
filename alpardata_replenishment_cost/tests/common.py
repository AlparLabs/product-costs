from __future__ import annotations

from odoo.tests.common import TransactionCase


class ReplenishmentCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main_company = cls.env['res.company'].create({'name': 'Matriz Test'})
        cls.branch = cls.env['res.company'].create({
            'name': 'Sucursal Test', 'parent_id': cls.main_company.id,
        })
        cls.independent = cls.env['res.company'].create({'name': 'Independiente Test'})
        cls.vendor = cls.env['res.partner'].create({'name': 'Proveedor Test'})
        cls.vendor_b = cls.env['res.partner'].create({'name': 'Proveedor B Test'})
        cls.product = cls.env['product.product'].create({
            'name': 'Producto Test',
            'replenishment_cost_type': 'supplier_price',
        })
        cls.template = cls.product.product_tmpl_id

    @classmethod
    def _seller(cls, price, company=None, partner=None, **vals):
        return cls.env['product.supplierinfo'].create({
            'partner_id': (partner or cls.vendor).id,
            'product_tmpl_id': cls.template.id,
            'company_id': company.id if company else False,
            'price': price,
            **vals,
        })
