# Promociones de Proveedor — Plan de implementación

> **Para agentes:** implementar tarea por tarea, en orden. Cada paso usa checkbox (`- [ ]`).
> Si usás superpowers: REQUIRED SUB-SKILL `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`.

**Goal:** Crear `alpardata_supplier_promotion`: promociones de proveedor con fechas que
cobran el precio promo en caja y ventas, toman el precio de compra especial (sell-in),
mandan los productos a la cola de etiquetas como promoción y calculan el monto a reclamar
al proveedor (sell-out).

**Architecture:** Un modelo `supplier.promotion` con líneas por producto. Al confirmar,
crea reglas de lista de precios con fechas (una por producto y lista), marcadas con
`supplier_promotion_line_id`; con el contexto `skip_supplier_promotions` esas reglas se
ignoran para obtener el precio regular. Las órdenes de compra aplican el precio especial en
los mismos tres caminos que la cascada del punto 1. El control de góndola del punto 3
suma el tipo de etiqueta (regular/promo) y la etiqueta 3x8 reutiliza su descuento manual
para mostrar "antes / ahora". La liquidación suma unidades vendidas en POS y ventas con
las listas de la promo.

**Tech Stack:** Odoo 19.0, `pytz`, `freezegun` (tests; viene con Odoo).

**Spec:** `docs/superpowers/specs/2026-09-24-supplier-promotion-design.md`
**Requisitos previos:** puntos 1 y 3 mergeados en `19.0`
(`alpardata_purchase_replacement_cost`, `alpardata_price_change_labels`).

---

## Convenciones

- **Rama:** `feat/supplier-promotion` desde `19.0`.
- Strings y commits en castellano: `feat(supplier_promotion): ...`.
- **Odoo 19:** `<list>`, `invisible="expr"`, `<chatter/>`, `<search>` sin
  `<group string>`, `models.Constraint`, `_read_group(domain, groupby, aggregates)`
  devuelve tuplas.
- Línea de OC: fijar precio sólo con `line._reset_price_unit(price)`; precio manual =
  `technical_price_unit != price_unit`.
- Fuente de Odoo: `C:\Users\Santiago\Desktop\Odoo\odoo-19.0`. Métodos que se extienden:
  `product.pricelist._get_applicable_rules_domain` (`addons/product/models/product_pricelist.py`),
  `purchase.order.line._prepare_purchase_order_line`,
  `purchase.order._update_order_line_info` y `_get_product_price_and_data`.
- **Tests:**

  ```bash
  odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_supplier_promotion --test-enable --test-tags /alpardata_supplier_promotion --stop-after-init --log-level=test
  ```

  Sin instancia: `python -m py_compile` + parseo XML con lxml; commit con
  `[tests no ejecutados]`.

## Mapa de archivos (nuevo, bajo `alpardata_supplier_promotion/`)

- `__init__.py`, `__manifest__.py`, `README.md`
- `models/__init__.py`
- `models/supplier_promotion.py` — cabecera: fechas, confirmar, liquidar, cerrar, cancelar
- `models/supplier_promotion_line.py` — líneas, búsqueda de promos vigentes, precio de compra
- `models/product_pricelist.py` — vínculo regla ↔ promo y exclusión por contexto
- `models/purchase_order_line.py`, `models/purchase_order.py` — sell-in
- `models/product_price_watch.py` — tipo de etiqueta y alerta "en promoción" (punto 3)
- `wizard/__init__.py`, `wizard/product_label_layout.py` — registrar etiqueta promo
- `report/__init__.py`, `report/product_label_report.py` — antes/ahora en la 3x8
- `data/ir_sequence.xml`
- `security/security.xml`, `security/ir.model.access.csv`
- `views/supplier_promotion_views.xml`, `views/purchase_order_views.xml`,
  `views/product_price_watch_views.xml`, `views/menus.xml`
- `tests/__init__.py`, `tests/common.py`, `tests/test_promotion_pricing.py`,
  `tests/test_purchase.py`, `tests/test_liquidation.py`, `tests/test_pos_liquidation.py`,
  `tests/test_labels.py`

---

### Tarea 1: Esqueleto, modelos y precio de venta promo

**Files:** Create el esqueleto, `models/supplier_promotion.py`,
`models/supplier_promotion_line.py`, `models/product_pricelist.py`, `data/ir_sequence.xml`,
`security/*`, `tests/common.py`, `tests/test_promotion_pricing.py`.

- [ ] **Paso 1: `__init__.py`**

```python
from . import models
from . import report
from . import wizard
```

- [ ] **Paso 2: `__manifest__.py`**

```python
{
    'name': 'AlparData - Promociones de Proveedor',
    'version': '19.0.1.0.0',
    'summary': 'Promociones de proveedor con fechas: precio promo en caja, precio de compra especial, etiquetas de promoción y liquidación de reintegros',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Inventory/Purchase',
    'depends': ['alpardata_price_change_labels', 'sale', 'point_of_sale'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
    ],  # la tarea 5 agrega las vistas
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

- [ ] **Paso 3: inits**

`models/__init__.py`:

```python
from . import supplier_promotion
from . import supplier_promotion_line
from . import product_pricelist
# from . import purchase_order_line
# from . import purchase_order
# from . import product_price_watch
```

`wizard/__init__.py`: `# from . import product_label_layout` —
`report/__init__.py`: `# from . import product_label_report`

`tests/__init__.py`:

```python
from . import test_promotion_pricing
# from . import test_purchase
# from . import test_liquidation
# from . import test_pos_liquidation
# from . import test_labels
```

- [ ] **Paso 4: `tests/common.py`**

```python
from __future__ import annotations

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class PromotionCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.today = fields.Date.today()
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Coca-Cola Test', 'purchase_discount_cascade': '10',
        })
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Góndola Test', 'currency_id': cls.company.currency_id.id,
        })
        cls.company.shelf_pricelist_id = cls.pricelist
        cls.product = cls.env['product.product'].create({
            'name': 'Coca 2,25 L',
            'list_price': 2399.0,
            'standard_price': 1000.0,
            'taxes_id': [(5, 0, 0)],
            'sale_ok': True,
        })
        cls.template = cls.product.product_tmpl_id
        cls.seller = cls.env['product.supplierinfo'].create({
            'partner_id': cls.vendor.id,
            'product_tmpl_id': cls.template.id,
            'price': 1200.0,
            'reference_cost': 1200.0,
        })

    def _promotion(self, start_offset=0, days=7, lines=None, **vals):
        start = self.today + timedelta(days=start_offset)
        return self.env['supplier.promotion'].create({
            'partner_id': self.vendor.id,
            'date_start': start,
            'date_end': start + timedelta(days=days - 1),
            'pricelist_ids': [(6, 0, self.pricelist.ids)],
            'line_ids': lines if lines is not None else [(0, 0, {
                'product_id': self.product.id,
                'promo_price': 1999.0,
                'purchase_price': 900.0,
                'reimbursement_amount': 300.0,
            })],
            **vals,
        })

    def _price(self, when, pricelist=None):
        return (pricelist or self.pricelist)._get_product_price(self.product, 1.0, date=when)
```

- [ ] **Paso 5: test que falla** — `tests/test_promotion_pricing.py`

```python
from __future__ import annotations

from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PromotionCommon


@tagged('post_install', '-at_install')
class TestPromotionPricing(PromotionCommon):

    def test_confirm_creates_dated_rules(self):
        promo = self._promotion()
        promo.action_confirm()
        self.assertEqual(promo.state, 'confirmed')
        items = promo.line_ids.pricelist_item_ids
        self.assertEqual(len(items), 1)
        self.assertEqual(items.fixed_price, 1999.0)
        self.assertEqual(items.date_start, promo.datetime_start)
        self.assertEqual(items.date_end, promo.datetime_end)

    def test_price_inside_and_outside(self):
        promo = self._promotion()
        promo.action_confirm()
        self.assertEqual(self._price(promo.datetime_start + timedelta(hours=1)), 1999.0)
        self.assertEqual(self._price(promo.datetime_end + timedelta(seconds=2)), 2399.0)

    def test_skip_context_gives_regular_price(self):
        promo = self._promotion()
        promo.action_confirm()
        inside = promo.datetime_start + timedelta(hours=1)
        regular = self.pricelist.with_context(skip_supplier_promotions=True)
        self.assertEqual(self._price(inside, regular), 2399.0)
        self.assertEqual(promo.line_ids.regular_price, 2399.0)

    def test_beats_replacement_formula(self):
        self.pricelist.write({'item_ids': [(0, 0, {
            'applied_on': '3_global', 'compute_price': 'formula',
            'base': 'replacement_cost', 'price_markup': 50.0,
        })]})
        promo = self._promotion()
        promo.action_confirm()
        self.assertEqual(self._price(promo.datetime_start + timedelta(hours=1)), 1999.0)

    def test_cancel_removes_rules(self):
        promo = self._promotion()
        promo.action_confirm()
        promo.action_cancel()
        self.assertEqual(promo.state, 'cancelled')
        self.assertFalse(promo.line_ids.pricelist_item_ids)
        self.assertEqual(self._price(promo.datetime_start + timedelta(hours=1)), 2399.0)

    def test_confirm_validations(self):
        with self.assertRaises(UserError):
            self._promotion(lines=[]).action_confirm()
        with self.assertRaises(UserError):
            self._promotion(sell_in=True, lines=[(0, 0, {
                'product_id': self.product.id, 'promo_price': 1999.0,
            })]).action_confirm()
        with self.assertRaises(UserError):
            self._promotion(sell_out=True, reimbursement_type='fixed', lines=[(0, 0, {
                'product_id': self.product.id, 'promo_price': 1999.0,
            })]).action_confirm()

    def test_overlap_rejected(self):
        self._promotion().action_confirm()
        with self.assertRaises(UserError):
            self._promotion(start_offset=3).action_confirm()

    def test_confirmed_is_locked(self):
        promo = self._promotion()
        promo.action_confirm()
        with self.assertRaises(UserError):
            promo.date_end = promo.date_end + timedelta(days=1)
        with self.assertRaises(UserError):
            promo.line_ids.promo_price = 1500.0

    def test_datetimes_cover_whole_days(self):
        promo = self._promotion()
        span = promo.datetime_end - promo.datetime_start
        self.assertEqual(span, timedelta(days=7) - timedelta(seconds=1))
```

- [ ] **Paso 6: correr** → falla.

- [ ] **Paso 7: `models/supplier_promotion.py`**

```python
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DEFAULT_TZ = 'America/Argentina/Buenos_Aires'
LOCKED_FIELDS = {
    'partner_id', 'company_id', 'date_start', 'date_end', 'pricelist_ids',
    'sell_in', 'sell_out', 'reimbursement_type', 'line_ids',
}


def _to_utc(tz, day, moment):
    local = tz.localize(datetime.combine(day, moment))
    return local.astimezone(pytz.utc).replace(tzinfo=None)


class SupplierPromotion(models.Model):
    _name = 'supplier.promotion'
    _description = 'Promoción de proveedor'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Número', readonly=True, copy=False, default='/')
    partner_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True, tracking=True, index=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_start = fields.Date(string='Desde', required=True, tracking=True)
    date_end = fields.Date(string='Hasta', required=True, tracking=True)
    datetime_start = fields.Datetime(compute='_compute_datetimes', store=True)
    datetime_end = fields.Datetime(compute='_compute_datetimes', store=True)
    pricelist_ids = fields.Many2many(
        'product.pricelist', string='Listas de precios',
        default=lambda self: self.env.company.shelf_pricelist_id,
        help='Listas donde rige el precio promo (la de las cajas y la de góndola).',
    )
    sell_in = fields.Boolean(string='Precio de compra especial', tracking=True)
    sell_out = fields.Boolean(string='Reintegro por unidad vendida', tracking=True)
    reimbursement_type = fields.Selection(
        [('fixed', 'Monto fijo por unidad'),
         ('difference', 'Diferencia entre precio regular y promo')],
        string='Reintegro', default='fixed',
    )
    state = fields.Selection(
        [('draft', 'Borrador'), ('confirmed', 'Confirmada'),
         ('done', 'Cerrada'), ('cancelled', 'Cancelada')],
        string='Estado', default='draft', required=True, tracking=True, copy=False,
    )
    line_ids = fields.One2many('supplier.promotion.line', 'promotion_id', string='Productos')
    revenue = fields.Monetary(string='Facturado en promo', compute='_compute_totals', store=True)
    amount_to_claim = fields.Monetary(
        string='Total a reclamar', compute='_compute_totals', store=True,
    )
    note = fields.Text(string='Notas')

    _dates_check = models.Constraint(
        'CHECK(date_end >= date_start)',
        'La fecha de fin no puede ser anterior a la de inicio.',
    )

    @api.depends('date_start', 'date_end', 'company_id')
    def _compute_datetimes(self) -> None:
        for rec in self:
            tz = pytz.timezone(rec.company_id.partner_id.tz or DEFAULT_TZ)
            rec.datetime_start = _to_utc(tz, rec.date_start, time.min) if rec.date_start else False
            rec.datetime_end = _to_utc(tz, rec.date_end, time(23, 59, 59)) if rec.date_end else False

    @api.depends('line_ids.revenue', 'line_ids.amount_to_claim')
    def _compute_totals(self) -> None:
        for rec in self:
            rec.revenue = sum(rec.line_ids.mapped('revenue'))
            rec.amount_to_claim = sum(rec.line_ids.mapped('amount_to_claim'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('supplier.promotion') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if LOCKED_FIELDS & set(vals) and any(rec.state != 'draft' for rec in self):
            raise UserError(_('Sólo se pueden modificar promociones en borrador.'))
        return super().write(vals)

    # ── Confirmar ─────────────────────────────────────────────────────────────
    def _check_can_confirm(self) -> None:
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Sólo se pueden confirmar promociones en borrador.'))
        if not self.line_ids:
            raise UserError(_('Cargá al menos un producto.'))
        if not self.pricelist_ids:
            raise UserError(_('Elegí al menos una lista de precios.'))
        for line in self.line_ids:
            name = line.product_id.display_name
            if line.promo_price <= 0:
                raise UserError(_('Falta el precio promo de %s.', name))
            if self.sell_in and line.purchase_price <= 0:
                raise UserError(_('Falta el precio de compra especial de %s.', name))
            if self.sell_out and self.reimbursement_type == 'fixed' and line.reimbursement_amount <= 0:
                raise UserError(_('Falta el reintegro por unidad de %s.', name))
        overlap = self.env['supplier.promotion.line'].search([
            ('promotion_id', '!=', self.id),
            ('promotion_id.state', '=', 'confirmed'),
            ('product_id', 'in', self.line_ids.product_id.ids),
            ('promotion_id.pricelist_ids', 'in', self.pricelist_ids.ids),
            ('promotion_id.date_start', '<=', self.date_end),
            ('promotion_id.date_end', '>=', self.date_start),
        ], limit=1)
        if overlap:
            raise UserError(_(
                '%(product)s ya está en la promoción %(promo)s en esas fechas.',
                product=overlap.product_id.display_name, promo=overlap.promotion_id.name,
            ))

    def _snapshot_regular_prices(self) -> None:
        pricelist = self.pricelist_ids[:1].with_context(skip_supplier_promotions=True)
        for line in self.line_ids:
            line.regular_price = pricelist._get_product_price(
                line.product_id, 1.0, date=self.datetime_start,
            )

    def _create_pricelist_items(self) -> None:
        vals_list = [
            {
                'pricelist_id': pricelist.id,
                'applied_on': '0_product_variant',
                'product_id': line.product_id.id,
                'product_tmpl_id': line.product_id.product_tmpl_id.id,
                'compute_price': 'fixed',
                'fixed_price': line.promo_price,
                'date_start': self.datetime_start,
                'date_end': self.datetime_end,
                'supplier_promotion_line_id': line.id,
            }
            for line in self.line_ids
            for pricelist in self.pricelist_ids
        ]
        # sudo: un usuario de compras puede no tener permiso sobre listas de precios
        self.env['product.pricelist.item'].sudo().create(vals_list)

    def action_confirm(self) -> None:
        for promo in self:
            promo._check_can_confirm()
            promo._snapshot_regular_prices()
            promo._create_pricelist_items()
        super(SupplierPromotion, self).write({'state': 'confirmed'})

    # ── Liquidación ───────────────────────────────────────────────────────────
    def _get_sold_data(self) -> dict[int, tuple[float, float]]:
        """{product_id: (unidades, facturado sin impuestos)} vendidas con una lista
        de la promo, dentro de las fechas, en POS y ventas."""
        self.ensure_one()
        products = self.line_ids.product_id
        result = defaultdict(lambda: [0.0, 0.0])
        pos_groups = self.env['pos.order.line'].sudo()._read_group(
            [
                ('product_id', 'in', products.ids),
                ('order_id.state', 'in', ('paid', 'done')),
                ('order_id.pricelist_id', 'in', self.pricelist_ids.ids),
                ('order_id.date_order', '>=', self.datetime_start),
                ('order_id.date_order', '<=', self.datetime_end),
                ('order_id.company_id', '=', self.company_id.id),
            ],
            ['product_id'], ['qty:sum', 'price_subtotal:sum'],
        )
        for product, qty, subtotal in pos_groups:
            result[product.id][0] += qty
            result[product.id][1] += subtotal
        sale_lines = self.env['sale.order.line'].sudo().search([
            ('product_id', 'in', products.ids),
            ('order_id.state', '=', 'sale'),
            ('order_id.pricelist_id', 'in', self.pricelist_ids.ids),
            ('order_id.date_order', '>=', self.datetime_start),
            ('order_id.date_order', '<=', self.datetime_end),
            ('company_id', '=', self.company_id.id),
        ])
        for sale_line in sale_lines:
            product = sale_line.product_id
            result[product.id][0] += sale_line.product_uom_id._compute_quantity(
                sale_line.product_uom_qty, product.uom_id,
            )
            result[product.id][1] += sale_line.price_subtotal
        return {product_id: (qty, amount) for product_id, (qty, amount) in result.items()}

    def action_compute_liquidation(self) -> None:
        for promo in self.filtered(lambda p: p.state in ('confirmed', 'done')):
            sold = promo._get_sold_data()
            for line in promo.line_ids:
                qty, revenue = sold.get(line.product_id.id, (0.0, 0.0))
                line.write({'qty_sold': qty, 'revenue': revenue})

    def action_done(self) -> None:
        today = fields.Date.context_today(self)
        for promo in self:
            if promo.state != 'confirmed':
                raise UserError(_('Sólo se pueden cerrar promociones confirmadas.'))
            if promo.date_end >= today:
                raise UserError(_('La promoción %s todavía no terminó.', promo.name))
        self.action_compute_liquidation()
        super(SupplierPromotion, self).write({'state': 'done'})

    # ── Cancelar ──────────────────────────────────────────────────────────────
    def action_cancel(self) -> None:
        if any(promo.state not in ('draft', 'confirmed') for promo in self):
            raise UserError(_('Sólo se pueden cancelar promociones en borrador o confirmadas.'))
        self.line_ids.pricelist_item_ids.sudo().unlink()
        super(SupplierPromotion, self).write({'state': 'cancelled'})

    def action_reset_draft(self) -> None:
        super(SupplierPromotion, self.filtered(lambda p: p.state == 'cancelled')).write(
            {'state': 'draft'},
        )
```

> `super(SupplierPromotion, self).write(...)` en las acciones escribe `state` sin pasar por
> el bloqueo de `write` (que sólo mira `LOCKED_FIELDS`; `state` no está, así que también
> funcionaría `self.write`). Se deja explícito para que quede claro que las acciones pueden
> cambiar el estado de promos no borrador.

- [ ] **Paso 8: `models/supplier_promotion_line.py`**

```python
from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LIQUIDATION_FIELDS = {'qty_sold', 'revenue', 'regular_price'}


class SupplierPromotionLine(models.Model):
    _name = 'supplier.promotion.line'
    _description = 'Producto de promoción de proveedor'
    _order = 'promotion_id, id'

    promotion_id = fields.Many2one(
        'supplier.promotion', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='promotion_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='promotion_id.currency_id')
    partner_id = fields.Many2one(
        related='promotion_id.partner_id', store=True, string='Proveedor',
    )
    state = fields.Selection(related='promotion_id.state', store=True, index=True)
    date_start = fields.Date(related='promotion_id.date_start', store=True)
    date_end = fields.Date(related='promotion_id.date_end', store=True)
    product_id = fields.Many2one(
        'product.product', string='Producto', required=True, index=True,
    )
    promo_price = fields.Float(string='Precio promo', digits='Product Price')
    regular_price = fields.Float(
        string='Precio regular', digits='Product Price', readonly=True,
        help='Precio de la lista al confirmar, sin la promoción.',
    )
    purchase_price = fields.Float(
        string='Precio de compra especial', digits='Product Price',
        help='Neto, en la unidad del producto y la moneda de la empresa.',
    )
    reimbursement_amount = fields.Float(string='Reintegro por unidad', digits='Product Price')
    reimbursement_unit = fields.Float(
        string='Reintegro unitario', digits='Product Price',
        compute='_compute_reimbursement_unit', store=True,
    )
    qty_sold = fields.Float(string='Unidades vendidas', readonly=True)
    revenue = fields.Monetary(string='Facturado', readonly=True)
    amount_to_claim = fields.Monetary(
        string='A reclamar', compute='_compute_amount_to_claim', store=True,
    )
    pricelist_item_ids = fields.One2many(
        'product.pricelist.item', 'supplier_promotion_line_id', string='Reglas de precio',
    )

    _product_uniq = models.Constraint(
        'UNIQUE(promotion_id, product_id)',
        'Un producto no puede repetirse en la misma promoción.',
    )

    @api.depends('promotion_id.sell_out', 'promotion_id.reimbursement_type',
                 'reimbursement_amount', 'regular_price', 'promo_price')
    def _compute_reimbursement_unit(self) -> None:
        for line in self:
            promo = line.promotion_id
            if not promo.sell_out:
                line.reimbursement_unit = 0.0
            elif promo.reimbursement_type == 'difference':
                line.reimbursement_unit = max(line.regular_price - line.promo_price, 0.0)
            else:
                line.reimbursement_unit = line.reimbursement_amount

    @api.depends('qty_sold', 'reimbursement_unit')
    def _compute_amount_to_claim(self) -> None:
        for line in self:
            line.amount_to_claim = line.qty_sold * line.reimbursement_unit

    @api.model_create_multi
    def create(self, vals_list):
        promotions = self.env['supplier.promotion'].browse(
            [vals['promotion_id'] for vals in vals_list if vals.get('promotion_id')]
        )
        if any(promo.state != 'draft' for promo in promotions):
            raise UserError(_('Sólo se pueden agregar productos a promociones en borrador.'))
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) - LIQUIDATION_FIELDS and any(line.state != 'draft' for line in self):
            raise UserError(_('Sólo se pueden modificar productos de promociones en borrador.'))
        return super().write(vals)

    def unlink(self):
        if any(line.state not in ('draft', False) for line in self):
            raise UserError(_('Sólo se pueden quitar productos de promociones en borrador.'))
        return super().unlink()

    # ── Búsquedas de promos vigentes ─────────────────────────────────────────
    @api.model
    def _find_active(self, template, company, when, pricelist=None):
        """Línea confirmada vigente en `when` para la plantilla `template`."""
        domain = [
            ('state', '=', 'confirmed'),
            ('company_id', '=', company.id),
            ('product_id.product_tmpl_id', '=', template.id),
            ('promotion_id.datetime_start', '<=', when),
            ('promotion_id.datetime_end', '>=', when),
        ]
        if pricelist:
            domain.append(('promotion_id.pricelist_ids', 'in', pricelist.ids))
        return self.sudo().search(domain, limit=1)

    @api.model
    def _find_purchase_promotion(self, product, partner, company, when):
        """Línea sell-in vigente en `when` para ese proveedor y producto."""
        if not product or not partner or not company:
            return self.browse()
        return self.sudo().search([
            ('state', '=', 'confirmed'),
            ('promotion_id.sell_in', '=', True),
            ('company_id', '=', company.id),
            ('product_id', '=', product.id),
            ('partner_id.commercial_partner_id', '=', partner.commercial_partner_id.id),
            ('promotion_id.datetime_start', '<=', when),
            ('promotion_id.datetime_end', '>=', when),
        ], limit=1)

    def _purchase_price_in(self, uom, currency, company, date) -> float:
        """Precio de compra especial convertido a `uom` y `currency`."""
        self.ensure_one()
        price = self.purchase_price
        product = self.product_id
        if uom and product.uom_id and uom != product.uom_id:
            price = product.uom_id._compute_price(price, uom)
        if currency and currency != company.currency_id:
            price = company.currency_id._convert(price, currency, company, date, round=False)
        return price
```

> `_snapshot_regular_prices` escribe `regular_price` antes de pasar a `confirmed`, y la
> liquidación escribe `qty_sold`/`revenue` con la promo confirmada: por eso están en
> `LIQUIDATION_FIELDS`.

- [ ] **Paso 9: `models/product_pricelist.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    supplier_promotion_line_id = fields.Many2one(
        'supplier.promotion.line', string='Promoción de proveedor',
        ondelete='cascade', index=True, readonly=True,
    )


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def _get_applicable_rules_domain(self, products, date, **kwargs):
        """Con `skip_supplier_promotions` en el contexto se ignoran las reglas
        creadas por promociones: así se obtiene el precio regular."""
        domain = super()._get_applicable_rules_domain(products, date, **kwargs)
        if self.env.context.get('skip_supplier_promotions'):
            domain = [*domain, ('supplier_promotion_line_id', '=', False)]
        return domain
```

- [ ] **Paso 10: `data/ir_sequence.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="seq_supplier_promotion" model="ir.sequence">
        <field name="name">Promociones de proveedor</field>
        <field name="code">supplier.promotion</field>
        <field name="prefix">PROM/%(year)s/</field>
        <field name="padding">4</field>
        <field name="company_id" eval="False"/>
    </record>
</odoo>
```

- [ ] **Paso 11: seguridad** — `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_supplier_promotion_user,supplier.promotion.user,model_supplier_promotion,purchase.group_purchase_user,1,1,1,0
access_supplier_promotion_manager,supplier.promotion.manager,model_supplier_promotion,purchase.group_purchase_manager,1,1,1,1
access_supplier_promotion_line_user,supplier.promotion.line.user,model_supplier_promotion_line,purchase.group_purchase_user,1,1,1,1
access_supplier_promotion_line_read,supplier.promotion.line.read,model_supplier_promotion_line,base.group_user,1,0,0,0
```

> La línea de lectura para `base.group_user` es necesaria porque el control de góndola, la
> etiqueta y las órdenes de compra consultan promos vigentes (igual usan `sudo`, pero el
> campo `promotion_line_id` del control de góndola se muestra a usuarios de inventario).

`security/security.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="rule_supplier_promotion_company" model="ir.rule">
        <field name="name">Promoción de proveedor: multi-empresa</field>
        <field name="model_id" ref="model_supplier_promotion"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    </record>
    <record id="rule_supplier_promotion_line_company" model="ir.rule">
        <field name="name">Producto de promoción: multi-empresa</field>
        <field name="model_id" ref="model_supplier_promotion_line"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    </record>
</odoo>
```

- [ ] **Paso 12: correr** → `TestPromotionPricing` pasa. Si `test_datetimes_cover_whole_days`
falla en un cambio de horario de verano, ignorarlo: Argentina no tiene horario de verano.

- [ ] **Paso 13: commit**

```bash
git add alpardata_supplier_promotion
git commit -m "feat(supplier_promotion): promociones con precio de venta por reglas de lista con fechas"
```

---

### Tarea 2: Precio de compra especial (sell-in)

**Files:** Create `models/purchase_order_line.py`, `models/purchase_order.py`,
`tests/test_purchase.py`.

- [ ] **Paso 1: test que falla** — `tests/test_purchase.py`

```python
from __future__ import annotations

from odoo.tests import tagged

from .common import PromotionCommon


@tagged('post_install', '-at_install')
class TestSellIn(PromotionCommon):

    def _po_line(self):
        po = self.env['purchase.order'].create({'partner_id': self.vendor.id})
        line = self.env['purchase.order.line'].create({
            'order_id': po.id, 'product_id': self.product.id, 'product_qty': 1.0,
        })
        return po, line

    def test_inside_dates_takes_special_price(self):
        self._promotion(sell_in=True).action_confirm()
        _po, line = self._po_line()
        self.assertEqual(line.price_unit, 900.0)
        self.assertEqual(line.discount, 0.0)
        self.assertFalse(line.discount_cascade)
        self.assertTrue(line.supplier_promotion_line_id)

    def test_outside_dates_keeps_list_and_cascade(self):
        self._promotion(start_offset=10, sell_in=True).action_confirm()
        _po, line = self._po_line()
        self.assertEqual(line.price_unit, 1200.0)
        self.assertAlmostEqual(line.discount, 10.0, places=2)
        self.assertFalse(line.supplier_promotion_line_id)

    def test_without_sell_in_ignored(self):
        self._promotion(sell_in=False).action_confirm()
        _po, line = self._po_line()
        self.assertEqual(line.price_unit, 1200.0)

    def test_manual_price_respected(self):
        self._promotion(sell_in=True).action_confirm()
        _po, line = self._po_line()
        line.price_unit = 950.0
        line.product_qty = 3.0
        self.assertEqual(line.price_unit, 950.0)

    def test_replenishment(self):
        self._promotion(sell_in=True).action_confirm()
        po = self.env['purchase.order'].create({'partner_id': self.vendor.id})
        vals = self.env['purchase.order.line']._prepare_purchase_order_line(
            self.product, 1.0, self.product.uom_id, self.company, self.vendor, po,
        )
        self.assertEqual(vals['price_unit'], 900.0)
        self.assertEqual(vals['discount'], 0.0)
        self.assertFalse(vals['discount_cascade'])

    def test_catalog(self):
        self._promotion(sell_in=True).action_confirm()
        po = self.env['purchase.order'].create({'partner_id': self.vendor.id})
        self.assertEqual(po._get_product_price_and_data(self.product)['price'], 900.0)
        self.assertEqual(po._update_order_line_info(self.product.id, 1.0), 900.0)

    def test_replacement_cost_untouched(self):
        self._promotion(sell_in=True).action_confirm()
        self.assertAlmostEqual(self.template.replacement_cost, 1080.0, places=2)
```

- [ ] **Paso 2: correr** → falla. Descomentar `test_purchase`.

- [ ] **Paso 3: `models/purchase_order_line.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    supplier_promotion_line_id = fields.Many2one(
        'supplier.promotion.line', string='Promoción', readonly=True, copy=False,
    )

    def _apply_supplier_promotion(self) -> None:
        """Precio de compra especial de una promo sell-in vigente a la fecha de la
        orden. Pisa la cascada del punto 1 (el precio especial ya es neto). No
        toca precios puestos a mano ni líneas facturadas."""
        Promotion = self.env['supplier.promotion.line']
        for line in self:
            if not line.product_id or line.invoice_lines or not line.company_id:
                continue
            if line.technical_price_unit != line.price_unit:
                continue
            order = line.order_id
            when = order.date_order or fields.Datetime.now()
            promo_line = Promotion._find_purchase_promotion(
                line.product_id, order.partner_id, line.company_id, when,
            )
            if not promo_line:
                line.supplier_promotion_line_id = False
                continue
            line._reset_price_unit(promo_line._purchase_price_in(
                line.product_uom_id, order.currency_id, line.company_id, when,
            ))
            line.discount = 0.0
            line.discount_cascade = False
            line.supplier_promotion_line_id = promo_line

    def _compute_price_unit_and_date_planned_and_name(self):
        super()._compute_price_unit_and_date_planned_and_name()
        self._apply_supplier_promotion()

    @api.model
    def _prepare_purchase_order_line(self, product_id, product_qty, product_uom,
                                     company_id, partner_id, po):
        vals = super()._prepare_purchase_order_line(
            product_id, product_qty, product_uom, company_id, partner_id, po,
        )
        when = po.date_order or fields.Datetime.now()
        promo_line = self.env['supplier.promotion.line']._find_purchase_promotion(
            product_id, partner_id, company_id, when,
        )
        if promo_line:
            uom = self.env['uom.uom'].browse(vals.get('product_uom_id')) or product_id.uom_id
            vals.update({
                'price_unit': promo_line._purchase_price_in(uom, po.currency_id, company_id, when),
                'discount': 0.0,
                'discount_cascade': False,
                'supplier_promotion_line_id': promo_line.id,
            })
        return vals
```

- [ ] **Paso 4: `models/purchase_order.py`**

```python
from __future__ import annotations

from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _update_order_line_info(self, product_id, quantity, *, section_id=False, **kwargs):
        price = super()._update_order_line_info(
            product_id, quantity, section_id=section_id, **kwargs
        )
        line = self.order_line.filtered(
            lambda pol: pol.product_id.id == product_id
            and pol.get_parent_section_line().id == section_id
        )[:1]
        if line:
            line._apply_supplier_promotion()
            return line.price_unit_discounted
        return price

    def _get_product_price_and_data(self, product):
        product_infos = super()._get_product_price_and_data(product)
        company = self.company_id or self.env.company
        when = self.date_order or fields.Datetime.now()
        promo_line = self.env['supplier.promotion.line']._find_purchase_promotion(
            product, self.partner_id, company, when,
        )
        if promo_line:
            product_infos['price'] = promo_line._purchase_price_in(
                product.uom_id, self.currency_id, company, when,
            )
        return product_infos
```

- [ ] **Paso 5: descomentar** `purchase_order_line` y `purchase_order` en `models/__init__.py`.

- [ ] **Paso 6: correr** → `TestSellIn` pasa. Correr también los tests de
`alpardata_purchase_replacement_cost` (no deben cambiar).

- [ ] **Paso 7: commit**

```bash
git add alpardata_supplier_promotion
git commit -m "feat(supplier_promotion): precio de compra especial en órdenes de compra (sell-in)"
```

---

### Tarea 3: Liquidación (sell-out)

**Files:** Create `tests/test_liquidation.py`, `tests/test_pos_liquidation.py`.
(La lógica ya está en `supplier.promotion._get_sold_data` de la tarea 1.)

- [ ] **Paso 1: `tests/test_liquidation.py`**

```python
from __future__ import annotations

from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import PromotionCommon


@tagged('post_install', '-at_install')
class TestSaleLiquidation(PromotionCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente Promo'})
        cls.other_pricelist = cls.env['product.pricelist'].create({'name': 'Mayorista Test'})

    def _sell(self, qty, pricelist=None):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'pricelist_id': (pricelist or self.pricelist).id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': qty})],
        })
        order.action_confirm()
        return order

    def test_fixed_reimbursement(self):
        promo = self._promotion(sell_out=True, reimbursement_type='fixed')
        promo.action_confirm()
        self._sell(3)
        self._sell(5, pricelist=self.other_pricelist)  # no cuenta
        promo.action_compute_liquidation()
        line = promo.line_ids
        self.assertEqual(line.qty_sold, 3.0)
        self.assertAlmostEqual(line.revenue, 3 * 1999.0, places=2)
        self.assertAlmostEqual(line.amount_to_claim, 900.0, places=2)
        self.assertAlmostEqual(promo.amount_to_claim, 900.0, places=2)

    def test_difference_reimbursement(self):
        promo = self._promotion(sell_out=True, reimbursement_type='difference')
        promo.action_confirm()
        self._sell(2)
        promo.action_compute_liquidation()
        self.assertAlmostEqual(promo.line_ids.reimbursement_unit, 400.0, places=2)
        self.assertAlmostEqual(promo.amount_to_claim, 800.0, places=2)

    def test_without_sell_out_nothing_to_claim(self):
        promo = self._promotion(sell_out=False)
        promo.action_confirm()
        self._sell(2)
        promo.action_compute_liquidation()
        self.assertEqual(promo.line_ids.qty_sold, 2.0)
        self.assertEqual(promo.amount_to_claim, 0.0)

    def test_done_only_after_end(self):
        promo = self._promotion(sell_out=True)
        promo.action_confirm()
        with self.assertRaises(UserError):
            promo.action_done()
        with freeze_time(promo.date_end + timedelta(days=1)):
            promo.action_done()
        self.assertEqual(promo.state, 'done')
```

- [ ] **Paso 2: `tests/test_pos_liquidation.py`**

```python
from __future__ import annotations

from datetime import timedelta

import odoo
from odoo import fields
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged('post_install', '-at_install')
class TestPosLiquidation(TestPoSCommon):

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.vendor = self.env['res.partner'].create({'name': 'Proveedor POS Promo'})
        self.product = self.create_product('Gaseosa POS', self.categ_basic, 20.0, 10.0)
        today = fields.Date.today()
        self.promo = self.env['supplier.promotion'].create({
            'partner_id': self.vendor.id,
            'date_start': today,
            'date_end': today + timedelta(days=6),
            'pricelist_ids': [(6, 0, self.config.pricelist_id.ids)],
            'sell_out': True,
            'reimbursement_type': 'fixed',
            'line_ids': [(0, 0, {
                'product_id': self.product.id, 'promo_price': 15.0,
                'reimbursement_amount': 3.0,
            })],
        })
        self.promo.action_confirm()

    def test_sale_and_refund(self):
        self.open_new_session()
        self.env['pos.order'].sync_from_ui([
            self.create_ui_order_data([(self.product, 2)]),
            self.create_ui_order_data([(self.product, -1)]),
        ])
        self.promo.action_compute_liquidation()
        self.assertEqual(self.promo.line_ids.qty_sold, 1.0)
        self.assertAlmostEqual(self.promo.amount_to_claim, 3.0, places=2)
```

> Si la configuración básica del POS de test no tiene `pricelist_id`, asignarle una lista en
> `setUp` antes de crear la promo (`self.config.pricelist_id = <lista nueva>`). Si
> `create_ui_order_data` no admite cantidades negativas, seguir el flujo de devolución de
> `odoo-19.0/addons/point_of_sale/tests/test_pos_margin.py`.

- [ ] **Paso 3: descomentar** ambos tests y **correr** → pasan.

- [ ] **Paso 4: commit**

```bash
git add alpardata_supplier_promotion
git commit -m "test(supplier_promotion): liquidación de reintegros en ventas y POS"
```

---

### Tarea 4: Etiquetas y control de góndola (integración con el punto 3)

**Files:** Create `models/product_price_watch.py`, `wizard/product_label_layout.py`,
`report/product_label_report.py`, `tests/test_labels.py`.

- [ ] **Paso 1: test que falla** — `tests/test_labels.py`

```python
from __future__ import annotations

from datetime import timedelta

from freezegun import freeze_time

from odoo.tests import tagged

from .common import PromotionCommon

LABEL_REPORT = 'report.product_label_3x8.report_producttemplatelabel3x8'


@tagged('post_install', '-at_install')
class TestPromotionLabels(PromotionCommon):

    def _watch(self):
        return self.env['product.price.watch']._refresh(self.template, self.company)

    def _print(self, fmt):
        self.env['product.label.layout'].create({
            'product_tmpl_ids': [(6, 0, self.template.ids)],
            'print_format': fmt,
            'pricelist_id': self.pricelist.id,
        }).process()

    def test_promo_label_cycle(self):
        # Etiqueta regular impresa antes de la promo
        self._print('3x8xprice')
        self.assertFalse(self._watch().label_pending)
        promo = self._promotion()
        promo.action_confirm()
        watch = self._watch()
        self.assertEqual(watch.promotion_line_id, promo.line_ids)
        self.assertEqual(watch.markup_alert, 'promo')
        self.assertTrue(watch.label_pending)
        # Imprimir la etiqueta de promo la saca de la cola
        self._print('3x8xpromo')
        watch = self._watch()
        self.assertFalse(watch.label_pending)
        self.assertEqual(watch.label_printed_kind, 'promo')
        self.assertEqual(watch.label_printed_price, 1999.0)
        # Terminada la promo, vuelve a la cola como regular
        with freeze_time(promo.datetime_end + timedelta(minutes=1)):
            watch = self._watch()
            self.assertFalse(watch.promotion_line_id)
            self.assertEqual(watch.label_expected_kind, 'regular')
            self.assertTrue(watch.label_pending)

    def test_regular_label_during_promo_stays_pending(self):
        self._promotion().action_confirm()
        self._print('3x8xprice')
        self.assertTrue(self._watch().label_pending)

    def test_label_info_before_and_now(self):
        self._promotion().action_confirm()
        info = self.env[LABEL_REPORT]._get_label_info(
            self.template, pricelist=self.pricelist, is_promo=True,
        )
        self.assertAlmostEqual(info['price_final'], 1999.0, places=2)
        self.assertAlmostEqual(info['price_before'], 2399.0, places=2)

    def test_label_info_without_promo_unchanged(self):
        info = self.env[LABEL_REPORT]._get_label_info(
            self.template, pricelist=self.pricelist, is_promo=True,
        )
        self.assertAlmostEqual(info['price_final'], 2399.0, places=2)
        self.assertFalse(info['price_before'])
```

> `freeze_time` con un `datetime` UTC: `datetime_end` está guardado en UTC, así que el
> minuto siguiente ya es fuera de la promo en cualquier zona horaria.

- [ ] **Paso 2: correr** → falla. Descomentar `test_labels`.

- [ ] **Paso 3: `models/product_price_watch.py`**

```python
from __future__ import annotations

from odoo import api, fields, models

LABEL_KINDS = [('regular', 'Regular'), ('promo', 'Promoción')]


class ProductPriceWatch(models.Model):
    _inherit = 'product.price.watch'

    promotion_line_id = fields.Many2one(
        'supplier.promotion.line', string='Promoción vigente', readonly=True,
    )
    label_expected_kind = fields.Selection(
        LABEL_KINDS, string='Etiqueta esperada',
        compute='_compute_label_expected_kind', store=True,
    )
    label_printed_kind = fields.Selection(
        LABEL_KINDS, string='Etiqueta impresa', default='regular',
    )
    markup_alert = fields.Selection(
        selection_add=[('promo', 'En promoción')],
        ondelete={'promo': 'set null'},
    )

    @api.depends('promotion_line_id')
    def _compute_label_expected_kind(self) -> None:
        for rec in self:
            rec.label_expected_kind = 'promo' if rec.promotion_line_id else 'regular'

    @api.depends('shelf_price', 'label_printed_price',
                 'label_expected_kind', 'label_printed_kind')
    def _compute_label_pending(self) -> None:
        super()._compute_label_pending()
        for rec in self:
            if (rec.label_printed_kind or 'regular') != rec.label_expected_kind:
                rec.label_pending = True

    @api.depends('shelf_price_untaxed', 'replacement_cost',
                 'product_tmpl_id.target_markup_pct', 'company_id.markup_tolerance_pct',
                 'promotion_line_id')
    def _compute_markup(self) -> None:
        super()._compute_markup()
        for rec in self.filtered('promotion_line_id'):
            rec.markup_alert = 'promo'

    @api.model
    def _refresh(self, templates, company):
        watches = super()._refresh(templates, company)
        now = fields.Datetime.now()
        Promotion = self.env['supplier.promotion.line']
        pricelist = company.shelf_pricelist_id or None
        for rec in watches:
            rec.promotion_line_id = Promotion._find_active(
                rec.product_tmpl_id, company, now, pricelist,
            )
        return watches

    @api.model
    def _mark_printed_promo(self, templates, company):
        """Registra la etiqueta de promo de los productos con promo vigente."""
        watches = self._refresh(templates, company).filtered('promotion_line_id')
        now = fields.Datetime.now()
        for rec in watches:
            rec.write({
                'label_printed_price': rec.shelf_price,
                'label_printed_date': now,
                'label_printed_kind': 'promo',
            })
        return watches
```

> Revisar en `alpardata_price_change_labels/models/product_price_watch.py` que los nombres
> `_compute_label_pending`, `_compute_markup`, `_refresh` y los campos coincidan con lo
> implementado en el punto 3; este archivo los extiende.

- [ ] **Paso 4: `wizard/product_label_layout.py`**

```python
from __future__ import annotations

from odoo import models


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    def process(self):
        action = super().process()
        templates = self.product_tmpl_ids or self.product_ids.product_tmpl_id
        Watch = self.env['product.price.watch'].sudo()
        if self.print_format == '3x8xpromo':
            Watch._mark_printed_promo(templates, self.env.company)
        elif self.print_format == '3x8xprice':
            # El punto 3 ya registró el precio impreso; acá sólo el tipo.
            Watch.search([
                ('product_tmpl_id', 'in', templates.ids),
                ('company_id', '=', self.env.company.id),
            ]).write({'label_printed_kind': 'regular'})
        return action
```

- [ ] **Paso 5: `report/product_label_report.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ReportProductTemplateLabel3x8(models.AbstractModel):
    _inherit = 'report.product_label_3x8.report_producttemplatelabel3x8'

    def _get_label_info(self, product, pricelist=None, is_promo=False,
                        loyalty_program=None, promo_discount=0.0):
        """Etiqueta de promo sin Loyalty ni descuento manual: si hay promoción de
        proveedor vigente, muestra "antes" (precio regular, sin reglas de promo) y
        "ahora" (precio promo) reutilizando el descuento manual de la etiqueta."""
        if is_promo and not loyalty_program and not promo_discount:
            template = product.product_tmpl_id if product._name == 'product.product' else product
            promo_line = self.env['supplier.promotion.line']._find_active(
                template, self.env.company, fields.Datetime.now(), pricelist or None,
            )
            if promo_line:
                regular_pricelist = (
                    pricelist.with_context(skip_supplier_promotions=True) if pricelist else None
                )
                regular = (
                    regular_pricelist._get_product_price(product, 1.0)
                    if regular_pricelist else product.list_price
                )
                if regular > promo_line.promo_price:
                    promo_discount = (1 - promo_line.promo_price / regular) * 100
                    pricelist = regular_pricelist
        return super()._get_label_info(
            product, pricelist=pricelist, is_promo=is_promo,
            loyalty_program=loyalty_program, promo_discount=promo_discount,
        )
```

> Verificar la firma de `_get_label_info` en
> `product_label_3x8/report/product_label_report.py` (hoy:
> `(self, product, pricelist=None, is_promo=False, loyalty_program=None, promo_discount=0.0)`).

- [ ] **Paso 6: descomentar** `product_price_watch` en `models/__init__.py`,
`product_label_layout` en `wizard/__init__.py` y `product_label_report` en
`report/__init__.py`.

- [ ] **Paso 7: correr** → `TestPromotionLabels` pasa. Correr también los tests de
`alpardata_price_change_labels` (no deben cambiar).

- [ ] **Paso 8: commit**

```bash
git add alpardata_supplier_promotion
git commit -m "feat(supplier_promotion): etiquetas de promoción y cola de góndola"
```

---

### Tarea 5: Vistas y menús

**Files:** Create las 4 vistas; Modify manifest.

- [ ] **Paso 1: `views/supplier_promotion_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="supplier_promotion_view_list" model="ir.ui.view">
        <field name="name">supplier.promotion.list</field>
        <field name="model">supplier.promotion</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="partner_id"/>
                <field name="date_start"/>
                <field name="date_end"/>
                <field name="sell_in" optional="show"/>
                <field name="sell_out" optional="show"/>
                <field name="currency_id" column_invisible="1"/>
                <field name="amount_to_claim" sum="Total" optional="show"/>
                <field name="state" widget="badge"
                       decoration-info="state == 'confirmed'"
                       decoration-success="state == 'done'"
                       decoration-muted="state == 'cancelled'"/>
            </list>
        </field>
    </record>

    <record id="supplier_promotion_view_form" model="ir.ui.view">
        <field name="name">supplier.promotion.form</field>
        <field name="model">supplier.promotion</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_confirm" type="object" string="Confirmar"
                            class="btn-primary" invisible="state != 'draft'"/>
                    <button name="action_compute_liquidation" type="object" string="Calcular liquidación"
                            invisible="state not in ('confirmed', 'done')"/>
                    <button name="action_done" type="object" string="Cerrar"
                            invisible="state != 'confirmed'"/>
                    <button name="action_cancel" type="object" string="Cancelar"
                            invisible="state not in ('draft', 'confirmed')"
                            confirm="Se quitan los precios promo de las listas. ¿Continuar?"/>
                    <button name="action_reset_draft" type="object" string="Volver a borrador"
                            invisible="state != 'cancelled'"/>
                    <field name="state" widget="statusbar" statusbar_visible="draft,confirmed,done"/>
                </header>
                <sheet>
                    <div class="oe_title">
                        <h1><field name="name"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="partner_id" readonly="state != 'draft'"/>
                            <field name="company_id" groups="base.group_multi_company"
                                   readonly="state != 'draft'"/>
                            <label for="date_start" string="Vigencia"/>
                            <div class="o_row">
                                <field name="date_start" readonly="state != 'draft'"/>
                                <span>a</span>
                                <field name="date_end" readonly="state != 'draft'"/>
                            </div>
                            <field name="pricelist_ids" widget="many2many_tags"
                                   readonly="state != 'draft'"/>
                        </group>
                        <group>
                            <field name="sell_in" readonly="state != 'draft'"/>
                            <field name="sell_out" readonly="state != 'draft'"/>
                            <field name="reimbursement_type" invisible="not sell_out"
                                   readonly="state != 'draft'"/>
                            <field name="currency_id" invisible="1"/>
                            <field name="revenue" invisible="state not in ('confirmed', 'done')"/>
                            <field name="amount_to_claim" invisible="not sell_out or state not in ('confirmed', 'done')"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Productos" name="lines">
                            <field name="line_ids" readonly="state != 'draft'">
                                <list editable="bottom">
                                    <field name="product_id"/>
                                    <field name="promo_price"/>
                                    <field name="regular_price" optional="show"/>
                                    <field name="purchase_price" column_invisible="not parent.sell_in"/>
                                    <field name="reimbursement_amount"
                                           column_invisible="not parent.sell_out or parent.reimbursement_type != 'fixed'"/>
                                    <field name="reimbursement_unit" column_invisible="not parent.sell_out"/>
                                    <field name="qty_sold" sum="Total"/>
                                    <field name="currency_id" column_invisible="1"/>
                                    <field name="revenue" sum="Total"/>
                                    <field name="amount_to_claim" sum="Total" column_invisible="not parent.sell_out"/>
                                </list>
                            </field>
                        </page>
                        <page string="Notas" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="supplier_promotion_view_search" model="ir.ui.view">
        <field name="name">supplier.promotion.search</field>
        <field name="model">supplier.promotion</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="partner_id"/>
                <filter name="filter_active" string="Vigentes"
                        domain="[('state', '=', 'confirmed'), ('date_start', '&lt;=', context_today().strftime('%Y-%m-%d')), ('date_end', '&gt;=', context_today().strftime('%Y-%m-%d'))]"/>
                <filter name="filter_confirmed" string="Confirmadas" domain="[('state', '=', 'confirmed')]"/>
                <filter name="filter_sell_out" string="Con reintegro" domain="[('sell_out', '=', True)]"/>
                <group>
                    <filter name="group_partner" string="Proveedor" context="{'group_by': 'partner_id'}"/>
                    <filter name="group_state" string="Estado" context="{'group_by': 'state'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_supplier_promotion" model="ir.actions.act_window">
        <field name="name">Promociones de proveedor</field>
        <field name="res_model">supplier.promotion</field>
        <field name="view_mode">list,form</field>
    </record>

    <record id="supplier_promotion_line_view_list" model="ir.ui.view">
        <field name="name">supplier.promotion.line.list</field>
        <field name="model">supplier.promotion.line</field>
        <field name="arch" type="xml">
            <list create="0" edit="0">
                <field name="promotion_id"/>
                <field name="partner_id"/>
                <field name="date_start"/>
                <field name="date_end"/>
                <field name="product_id"/>
                <field name="promo_price"/>
                <field name="qty_sold" sum="Total"/>
                <field name="currency_id" column_invisible="1"/>
                <field name="revenue" sum="Total"/>
                <field name="amount_to_claim" sum="Total"/>
                <field name="state" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="action_supplier_promotion_line" model="ir.actions.act_window">
        <field name="name">Liquidación de promociones</field>
        <field name="res_model">supplier.promotion.line</field>
        <field name="view_mode">list</field>
        <field name="domain">[('state', 'in', ('confirmed', 'done'))]</field>
        <field name="context">{'group_by': ['partner_id', 'promotion_id']}</field>
    </record>
</odoo>
```

- [ ] **Paso 2: `views/purchase_order_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="purchase_order_form_supplier_promotion" model="ir.ui.view">
        <field name="name">purchase.order.form.supplier.promotion</field>
        <field name="model">purchase.order</field>
        <field name="inherit_id" ref="purchase.purchase_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='order_line']/list/field[@name='discount']" position="after">
                <field name="supplier_promotion_line_id" optional="hide" force_save="1"/>
            </xpath>
        </field>
    </record>
</odoo>
```

> `force_save="1"` es obligatorio: el campo es readonly y lo pone el onchange. Sin eso el
> cliente web no lo envía al guardar (mismo problema que tuvo `discount_cascade` en el
> punto 1).

- [ ] **Paso 3: `views/product_price_watch_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_price_watch_list_labels_promotion" model="ir.ui.view">
        <field name="name">product.price.watch.list.labels.promotion</field>
        <field name="model">product.price.watch</field>
        <field name="inherit_id" ref="alpardata_price_change_labels.product_price_watch_view_list_labels"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='shelf_price']" position="after">
                <field name="label_expected_kind" widget="badge"
                       decoration-warning="label_expected_kind == 'promo'"/>
                <field name="promotion_line_id" optional="show"/>
            </xpath>
        </field>
    </record>
</odoo>
```

> El botón "Imprimir etiquetas" del punto 3 abre el wizard con formato regular. Para las
> etiquetas de promo, el usuario filtra por "Etiqueta esperada = Promoción" y elige el
> formato "3 x 8 Promoción / Descuento" en el wizard.

- [ ] **Paso 4: `views/menus.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_supplier_promotion"
              name="Promociones de proveedor"
              parent="purchase.menu_purchase_products"
              action="action_supplier_promotion"
              sequence="35"/>
    <menuitem id="menu_supplier_promotion_line"
              name="Liquidación de promociones"
              parent="purchase.menu_purchase_products"
              action="action_supplier_promotion_line"
              sequence="36"/>
</odoo>
```

- [ ] **Paso 5: manifest `data`**:

```python
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/supplier_promotion_views.xml',
        'views/purchase_order_views.xml',
        'views/product_price_watch_views.xml',
        'views/menus.xml',
    ],
```

- [ ] **Paso 6: actualizar el módulo y correr todos los tests** → 0 fallas.

- [ ] **Paso 7: prueba manual** (anotar en el PR): promo de la Coca del día de hoy a 7
días, sell-in y sell-out; confirmarla; abrir el POS → cobra $1.999; OC al proveedor → $900
sin bonificación; "Etiquetas pendientes" → aparece como Promoción; imprimir 3x8 promo →
"antes $2.399 / ahora $1.999"; vender 2 en el POS → "Calcular liquidación" da 2 unidades y
el monto a reclamar.

- [ ] **Paso 8: commit**

```bash
git add alpardata_supplier_promotion
git commit -m "feat(supplier_promotion): vistas, liquidación y menús"
```

---

### Tarea 6: README y PR

- [ ] **Paso 1: `README.md`**: qué es una promo de proveedor y por qué no se carga como
costo; sell-in vs sell-out (y que pueden combinarse); cómo funciona el precio (regla con
fechas en las listas elegidas; la caja tiene que usar una de esas listas); qué pasa en las
OC; ciclo de etiquetas (entra a la cola como promo, sale al imprimir la 3x8 de promoción,
vuelve como regular al terminar); cómo se calcula el monto a reclamar (unidades vendidas
con una lista de la promo, dentro de las fechas; las devoluciones restan) y que la nota de
crédito se carga en Contabilidad como siempre.
- [ ] **Paso 2: commit, push y PR contra `19.0`.**

```bash
git add alpardata_supplier_promotion/README.md
git commit -m "docs(supplier_promotion): README"
git push -u origin feat/supplier-promotion
```
