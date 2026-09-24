# Margen de Reposición en Ventas y POS — Plan de implementación

> **Para agentes:** implementar tarea por tarea, en orden. Cada paso usa checkbox (`- [ ]`).
> Si usás superpowers: REQUIRED SUB-SKILL `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`.

**Goal:** Crear `alpardata_sale_replacement_margin` y `alpardata_pos_replacement_margin`:
guardar en cada línea de venta y de POS el costo de reposición unitario al momento de la
venta y calcular el margen de reposición, disponible en los análisis junto al margen
estándar.

**Architecture:** Dos módulos independientes (ventas y POS) que usan el helper
`product.product._get_replacement_cost_for(company, uom, currency, date)` del punto 1.
Los campos son computados almacenados; en ventas se recalculan al confirmar. Los
reportes SQL (`sale.report`, `report.pos.order`) suman el margen con la misma expresión
que el margen estándar.

**Tech Stack:** Odoo 19.0 (`sale_margin`, `point_of_sale`).

**Spec:** `docs/superpowers/specs/2026-09-24-replacement-margin-design.md`
**Requisito previo:** punto 1 mergeado (helper `_get_replacement_cost_for`).

---

## Convenciones

- **Rama:** `feat/replacement-margin` desde `19.0`.
- Strings y commits en castellano: `feat(sale_replacement_margin): ...`,
  `feat(pos_replacement_margin): ...`.
- **Odoo 19:** `<list>`, `invisible="expr"`, `column_invisible` en columnas de listas.
- Fuente de Odoo: `C:\Users\Santiago\Desktop\Odoo\odoo-19.0` — mirar
  `addons/sale_margin/` y `addons/point_of_sale/models/pos_order.py` (`PosOrderLine`,
  `_compute_margin`) antes de empezar: este plan copia sus patrones.
- **Tests:**

  ```bash
  odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_sale_replacement_margin,alpardata_pos_replacement_margin --test-enable --test-tags /alpardata_sale_replacement_margin,/alpardata_pos_replacement_margin --stop-after-init --log-level=test
  ```

## Mapa de archivos

`alpardata_sale_replacement_margin/`:
- `__init__.py`, `__manifest__.py`, `README.md`
- `models/__init__.py`, `models/sale_order_line.py`, `models/sale_order.py`
- `report/__init__.py`, `report/sale_report.py`
- `views/sale_order_views.xml`
- `tests/__init__.py`, `tests/test_sale_replacement_margin.py`

`alpardata_pos_replacement_margin/`:
- `__init__.py`, `__manifest__.py`, `README.md`
- `models/__init__.py`, `models/pos_order.py` (orden y línea)
- `report/__init__.py`, `report/pos_order_report.py`
- `views/pos_order_views.xml`
- `tests/__init__.py`, `tests/test_pos_replacement_margin.py`

---

### Tarea 1: Ventas — campos en la línea y en el pedido

**Files:** Create el esqueleto de `alpardata_sale_replacement_margin`, modelos y test.

- [ ] **Paso 1: `__init__.py`** — incluye el `pre_init_hook` que crea las columnas
vacías **antes** de instalar, para que el ORM no recalcule el costo de reposición de
pedidos históricos con el costo de hoy (decisión del spec: los históricos quedan en 0).

```python
from . import models
from . import report


def pre_init_hook(env):
    """Crea las columnas en 0: los pedidos anteriores a la instalación no se
    recalculan (quedarían con el costo de hoy, que es el dato engañoso)."""
    env.cr.execute("""
        ALTER TABLE sale_order_line
            ADD COLUMN IF NOT EXISTS replacement_cost_unit double precision DEFAULT 0,
            ADD COLUMN IF NOT EXISTS replacement_cost_fallback boolean DEFAULT false,
            ADD COLUMN IF NOT EXISTS replacement_margin double precision DEFAULT 0,
            ADD COLUMN IF NOT EXISTS replacement_margin_percent double precision DEFAULT 0;
        ALTER TABLE sale_order
            ADD COLUMN IF NOT EXISTS replacement_margin numeric DEFAULT 0,
            ADD COLUMN IF NOT EXISTS replacement_margin_percent double precision DEFAULT 0;
    """)
```

`__manifest__.py`:

```python
{
    'name': 'AlparData - Margen de Reposición en Ventas',
    'version': '19.0.1.0.0',
    'summary': 'Margen de ventas calculado contra el costo de reposición (además del margen contable)',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Sales/Sales',
    'depends': ['sale_margin', 'alpardata_purchase_replacement_cost'],
    'data': [],  # la tarea 3 agrega las vistas
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

`models/__init__.py`:

```python
from . import sale_order_line
from . import sale_order
```

`report/__init__.py`:

```python
# from . import sale_report
```

`tests/__init__.py`:

```python
from . import test_sale_replacement_margin
```

- [ ] **Paso 2: test que falla** — `tests/test_sale_replacement_margin.py`

```python
from __future__ import annotations

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestSaleReplacementMargin(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Cliente Test'})
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Proveedor Test', 'purchase_discount_cascade': '10',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Aceite 1L',
            'standard_price': 700.0,
            'list_price': 1500.0,
            'taxes_id': [(5, 0, 0)],
        })
        cls.seller = cls.env['product.supplierinfo'].create({
            'partner_id': cls.vendor.id,
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'price': 1000.0,
            'reference_cost': 1000.0,  # reposición = 900 (bonif. 10)
        })

    def _order(self, qty=2.0, uom=None, currency=None):
        vals = {'partner_id': self.customer.id}
        if currency:
            pricelist = self.env['product.pricelist'].create({
                'name': f'Lista {currency.name}', 'currency_id': currency.id,
            })
            vals['pricelist_id'] = pricelist.id
        line = {'product_id': self.product.id, 'product_uom_qty': qty, 'price_unit': 1500.0}
        if uom:
            line['product_uom_id'] = uom.id
        vals['order_line'] = [(0, 0, line)]
        return self.env['sale.order'].create(vals)

    def test_line_values(self):
        order = self._order()
        line = order.order_line
        self.assertAlmostEqual(line.replacement_cost_unit, 900.0, places=2)
        self.assertFalse(line.replacement_cost_fallback)
        self.assertAlmostEqual(line.replacement_margin, 3000.0 - 1800.0, places=2)
        self.assertAlmostEqual(line.replacement_margin_percent, 0.4, places=4)
        self.assertAlmostEqual(order.replacement_margin, 1200.0, places=2)
        self.assertAlmostEqual(order.replacement_margin_percent, 0.4, places=4)

    def test_standard_margin_untouched(self):
        line = self._order().order_line
        self.assertAlmostEqual(line.purchase_price, 700.0, places=2)
        self.assertAlmostEqual(line.margin, 3000.0 - 1400.0, places=2)

    def test_line_uom_dozen(self):
        dozen = self.env.ref('uom.product_uom_dozen')
        line = self._order(qty=1.0, uom=dozen).order_line
        self.assertAlmostEqual(line.replacement_cost_unit, 900.0 * 12, places=2)

    def test_order_in_usd(self):
        usd = self.env.ref('base.USD')
        usd.active = True
        if self.env.company.currency_id == usd:
            self.skipTest('La empresa de test ya usa USD')
        self.env['res.currency.rate'].create({
            'currency_id': usd.id, 'company_id': self.env.company.id,
            'name': fields.Date.today(), 'rate': 1 / 1000,
        })
        line = self._order(currency=usd).order_line
        self.assertAlmostEqual(line.replacement_cost_unit, 0.9, places=4)

    def test_fallback_to_avco(self):
        self.seller.unlink()
        line = self._order().order_line
        self.assertTrue(line.replacement_cost_fallback)
        self.assertAlmostEqual(line.replacement_cost_unit, 700.0, places=2)

    def test_recomputed_on_confirm(self):
        order = self._order()
        self.seller.reference_cost = 1200.0  # reposición 1080
        self.assertAlmostEqual(order.order_line.replacement_cost_unit, 900.0, places=2)
        order.action_confirm()
        self.assertAlmostEqual(order.order_line.replacement_cost_unit, 1080.0, places=2)
        self.assertAlmostEqual(order.replacement_margin, 3000.0 - 2160.0, places=2)
```

- [ ] **Paso 3: correr** → falla.

- [ ] **Paso 4: `models/sale_order_line.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    replacement_cost_unit = fields.Float(
        string='Costo de reposición',
        compute='_compute_replacement_cost_unit',
        store=True,
        precompute=True,
        copy=False,
        min_display_digits='Product Price',
        groups='base.group_user',
        help='Costo de reposición unitario al cargar la línea; se actualiza al confirmar.',
    )
    replacement_cost_fallback = fields.Boolean(
        string='Costo AVCO (sin reposición)',
        compute='_compute_replacement_cost_unit',
        store=True,
        precompute=True,
        copy=False,
        groups='base.group_user',
    )
    replacement_margin = fields.Float(
        string='Margen de reposición',
        compute='_compute_replacement_margin',
        store=True,
        digits='Product Price',
        groups='base.group_user',
    )
    replacement_margin_percent = fields.Float(
        string='Margen de reposición (%)',
        compute='_compute_replacement_margin',
        store=True,
        groups='base.group_user',
    )

    @api.depends('product_id', 'company_id', 'currency_id', 'product_uom_id')
    def _compute_replacement_cost_unit(self) -> None:
        for line in self:
            if not line.product_id:
                line.replacement_cost_unit = 0.0
                line.replacement_cost_fallback = False
                continue
            company = line.company_id or self.env.company
            date = line.order_id.date_order or fields.Datetime.now()
            cost, is_fallback = line.product_id._get_replacement_cost_for(
                company,
                line.product_uom_id or line.product_id.uom_id,
                line.currency_id or company.currency_id,
                fields.Date.to_date(date),
            )
            line.replacement_cost_unit = cost
            line.replacement_cost_fallback = is_fallback

    @api.depends('price_subtotal', 'product_uom_qty', 'replacement_cost_unit')
    def _compute_replacement_margin(self) -> None:
        for line in self:
            line.replacement_margin = (
                line.price_subtotal - line.replacement_cost_unit * line.product_uom_qty
            )
            line.replacement_margin_percent = (
                line.price_subtotal and line.replacement_margin / line.price_subtotal
            )

    def _refresh_replacement_cost(self) -> None:
        """Fuerza el recálculo del costo de reposición (y del margen que depende
        de él) con los datos de hoy."""
        fields_to_compute = [
            self._fields['replacement_cost_unit'],
            self._fields['replacement_cost_fallback'],
        ]
        for field in fields_to_compute:
            self.env.add_to_compute(field, self)
        self.flush_recordset(['replacement_cost_unit', 'replacement_cost_fallback'])
```

> `add_to_compute` + `flush` es el patrón del core para forzar recomputes de campos
> almacenados. Como `replacement_margin` depende de `replacement_cost_unit`, se recalcula
> solo. Si el test `test_recomputed_on_confirm` muestra el margen viejo, agregar también
> `replacement_margin` y `replacement_margin_percent` a `fields_to_compute`.

- [ ] **Paso 5: `models/sale_order.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    replacement_margin = fields.Monetary(
        string='Margen de reposición',
        compute='_compute_replacement_margin',
        store=True,
        groups='base.group_user',
    )
    replacement_margin_percent = fields.Float(
        string='Margen de reposición (%)',
        compute='_compute_replacement_margin',
        store=True,
        aggregator='avg',
        groups='base.group_user',
    )

    @api.depends('order_line.replacement_margin', 'amount_untaxed')
    def _compute_replacement_margin(self) -> None:
        for order in self:
            order.replacement_margin = sum(order.order_line.mapped('replacement_margin'))
            order.replacement_margin_percent = (
                order.amount_untaxed and order.replacement_margin / order.amount_untaxed
            )

    def action_confirm(self):
        # Un presupuesto puede quedar semanas abierto: con inflación, el costo que
        # importa es el del día de la venta.
        self.order_line.filtered('product_id')._refresh_replacement_cost()
        return super().action_confirm()
```

- [ ] **Paso 6: correr** → `TestSaleReplacementMargin` pasa.

- [ ] **Paso 7: commit**

```bash
git add alpardata_sale_replacement_margin
git commit -m "feat(sale_replacement_margin): costo y margen de reposición en pedidos de venta"
```

---

### Tarea 2: Ventas — análisis de ventas

**Files:** Create `report/sale_report.py`; Modify `report/__init__.py`, test.

- [ ] **Paso 1: agregar test** al final de la clase de `tests/test_sale_replacement_margin.py`:

```python
    def test_sale_report(self):
        order = self._order()
        order.action_confirm()
        self.env.flush_all()
        data = self.env['sale.report']._read_group(
            [('order_reference', '=', f'sale.order,{order.id}')],
            [], ['replacement_margin:sum'],
        )
        self.assertAlmostEqual(data[0][0], 1200.0, places=2)
```

> Verificar en `odoo-19.0/addons/sale/report/sale_report.py` el nombre del campo que
> referencia al pedido (`order_reference` en 19). Si es otro, filtrar por ese.

- [ ] **Paso 2: `report/sale_report.py`** (copia del patrón de `sale_margin`)

```python
from __future__ import annotations

from odoo import fields, models


class SaleReport(models.Model):
    _inherit = 'sale.report'

    replacement_margin = fields.Float(string='Margen de reposición')

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['replacement_margin'] = f"""SUM(l.replacement_margin
            / {self._case_value_or_one('s.currency_rate')}
            * {self._case_value_or_one('account_currency_table.rate')})
        """
        return res
```

Descomentar en `report/__init__.py`.

- [ ] **Paso 3: correr** → pasa.

- [ ] **Paso 4: commit**

```bash
git add alpardata_sale_replacement_margin
git commit -m "feat(sale_replacement_margin): margen de reposición en el análisis de ventas"
```

---

### Tarea 3: Ventas — vistas

**Files:** Create `views/sale_order_views.xml`; Modify manifest.

- [ ] **Paso 1: `views/sale_order_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="sale_order_form_replacement_margin" model="ir.ui.view">
        <field name="name">sale.order.form.replacement.margin</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale_margin.sale_margin_sale_order"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='margin']/../.." position="after">
                <div class="d-flex float-end" colspan="2" groups="base.group_user">
                    <label for="replacement_margin"/>
                    <div>
                        <field name="replacement_margin" class="oe_inline"/>
                        <span class="oe_inline" invisible="amount_untaxed == 0">
                            (<field name="replacement_margin_percent" nolabel="1"
                                    class="oe_inline" widget="percentage"/>)
                        </span>
                    </div>
                </div>
            </xpath>
            <xpath expr="//field[@name='order_line']//list//field[@name='purchase_price']" position="after">
                <field name="replacement_cost_unit" optional="hide"/>
                <field name="replacement_margin_percent" optional="hide" widget="percentage"/>
            </xpath>
        </field>
    </record>
</odoo>
```

> Si el primer xpath no matchea (depende de cómo `sale_margin` arma el bloque del margen
> en `sale_margin/views/sale_order_views.xml`), anclar a
> `//field[@name='tax_totals']` con `position="after"`.

- [ ] **Paso 2: manifest** `'data': ['views/sale_order_views.xml'],`

- [ ] **Paso 3: actualizar el módulo y correr tests** → sin errores de vista, 0 fallas.

- [ ] **Paso 4: commit**

```bash
git add alpardata_sale_replacement_margin
git commit -m "feat(sale_replacement_margin): vistas de pedido de venta"
```

---

### Tarea 4: POS — campos en la línea y en la orden

**Files:** Create el esqueleto de `alpardata_pos_replacement_margin`, modelo y test.

- [ ] **Paso 1: `__init__.py`** — mismo criterio de columnas vacías que en ventas:

```python
from . import models
from . import report


def pre_init_hook(env):
    """Crea las columnas en 0: las órdenes anteriores a la instalación no se recalculan."""
    env.cr.execute("""
        ALTER TABLE pos_order_line
            ADD COLUMN IF NOT EXISTS replacement_cost_unit double precision DEFAULT 0,
            ADD COLUMN IF NOT EXISTS replacement_margin numeric DEFAULT 0;
        ALTER TABLE pos_order
            ADD COLUMN IF NOT EXISTS replacement_margin numeric DEFAULT 0;
    """)
```

`__manifest__.py`:

```python
{
    'name': 'AlparData - Margen de Reposición en POS',
    'version': '19.0.1.0.0',
    'summary': 'Margen del punto de venta calculado contra el costo de reposición',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Sales/Point of Sale',
    'depends': ['point_of_sale', 'alpardata_purchase_replacement_cost'],
    'data': [],  # la tarea 6 agrega las vistas
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

`models/__init__.py`: `from . import pos_order` —
`report/__init__.py`: `# from . import pos_order_report` —
`tests/__init__.py`: `from . import test_pos_replacement_margin`

- [ ] **Paso 2: test que falla** — `tests/test_pos_replacement_margin.py`

```python
from __future__ import annotations

import odoo
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged('post_install', '-at_install')
class TestPosReplacementMargin(TestPoSCommon):

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        vendor = self.env['res.partner'].create({
            'name': 'Proveedor POS', 'purchase_discount_cascade': '10',
        })
        # precio 10, AVCO 5, lista 6 → reposición 5,40
        self.product = self.create_product('Galletitas', self.categ_basic, 10, 5)
        self.env['product.supplierinfo'].create({
            'partner_id': vendor.id,
            'product_tmpl_id': self.product.product_tmpl_id.id,
            'price': 6.0,
            'reference_cost': 6.0,
        })

    def _sync(self, lines):
        self.open_new_session()
        self.env['pos.order'].sync_from_ui([self.create_ui_order_data(lines)])
        return self.pos_session.order_ids[0]

    def test_sale(self):
        order = self._sync([(self.product, 2)])
        line = order.lines
        self.assertAlmostEqual(line.replacement_cost_unit, 5.4, places=4)
        self.assertAlmostEqual(line.replacement_margin, 20.0 - 10.8, places=4)
        self.assertAlmostEqual(order.replacement_margin, 9.2, places=4)

    def test_refund_is_negative(self):
        order = self._sync([(self.product, -1)])
        self.assertAlmostEqual(order.lines.replacement_margin, -10.0 + 5.4, places=4)

    def test_report(self):
        order = self._sync([(self.product, 2)])
        self.env.flush_all()
        data = self.env['report.pos.order']._read_group(
            [('order_id', '=', order.id)], [], ['replacement_margin:sum'],
        )
        self.assertAlmostEqual(data[0][0], 9.2, places=2)
```

> Revisar `odoo-19.0/addons/point_of_sale/tests/test_pos_margin.py`: este test sigue su
> estructura. Si `create_ui_order_data` no acepta cantidades negativas para simular una
> devolución, usar el flujo de devolución de ese mismo archivo (`refund`).

- [ ] **Paso 3: correr** → falla.

- [ ] **Paso 4: `models/pos_order.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    replacement_cost_unit = fields.Float(
        string='Costo de reposición',
        compute='_compute_replacement_cost_unit',
        store=True,
        min_display_digits='Product Price',
        help='Costo de reposición unitario a la fecha de la venta.',
    )
    replacement_margin = fields.Monetary(
        string='Margen de reposición',
        compute='_compute_replacement_margin',
        store=True,
    )

    @api.depends('product_id', 'order_id.company_id', 'order_id.currency_id')
    def _compute_replacement_cost_unit(self) -> None:
        for line in self:
            order = line.order_id
            if not line.product_id or line.product_id.type == 'combo' or not order:
                line.replacement_cost_unit = 0.0
                continue
            company = order.company_id
            cost, _is_fallback = line.product_id._get_replacement_cost_for(
                company,
                line.product_id.uom_id,
                order.currency_id or company.currency_id,
                fields.Date.to_date(order.date_order or fields.Datetime.now()),
            )
            line.replacement_cost_unit = cost

    @api.depends('price_subtotal', 'qty', 'replacement_cost_unit')
    def _compute_replacement_margin(self) -> None:
        for line in self:
            line.replacement_margin = line.price_subtotal - line.replacement_cost_unit * line.qty


class PosOrder(models.Model):
    _inherit = 'pos.order'

    replacement_margin = fields.Monetary(
        string='Margen de reposición',
        compute='_compute_replacement_margin',
        store=True,
    )

    @api.depends('lines.replacement_margin')
    def _compute_replacement_margin(self) -> None:
        for order in self:
            order.replacement_margin = sum(order.lines.mapped('replacement_margin'))
```

> `pos.order.line` tiene `currency_id` (related a la orden), por eso `Monetary` funciona
> sin declarar `currency_field`. Verificarlo en `pos_order.py` (`class PosOrderLine`).

- [ ] **Paso 5: correr** → `test_sale` y `test_refund_is_negative` pasan.

- [ ] **Paso 6: commit**

```bash
git add alpardata_pos_replacement_margin
git commit -m "feat(pos_replacement_margin): costo y margen de reposición en órdenes de POS"
```

---

### Tarea 5: POS — análisis

**Files:** Create `report/pos_order_report.py`.

- [ ] **Paso 1: `report/pos_order_report.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ReportPosOrder(models.Model):
    _inherit = 'report.pos.order'

    replacement_margin = fields.Float(string='Margen de reposición', readonly=True)

    def _select(self):
        # Misma conversión de moneda que el campo `margin` del reporte estándar.
        return super()._select() + """,
                l.replacement_margin / COALESCE(NULLIF(s.currency_rate, 0), 1.0) AS replacement_margin
        """
```

Descomentar en `report/__init__.py`.

> `_select()` del core termina en `fpc.id AS pos_categ_id` sin coma final; por eso se
> agrega `,` al principio. Si en tu versión `_select` termina distinto, abrir
> `odoo-19.0/addons/point_of_sale/report/pos_order_report.py` y ajustar.

- [ ] **Paso 2: correr** → `test_report` pasa.

- [ ] **Paso 3: commit**

```bash
git add alpardata_pos_replacement_margin
git commit -m "feat(pos_replacement_margin): margen de reposición en el análisis de POS"
```

---

### Tarea 6: POS — vistas

- [ ] **Paso 1: `views/pos_order_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_pos_pos_form_replacement_margin" model="ir.ui.view">
        <field name="name">pos.order.form.replacement.margin</field>
        <field name="model">pos.order</field>
        <field name="inherit_id" ref="point_of_sale.view_pos_pos_form"/>
        <field name="arch" type="xml">
            <xpath expr="//label[@for='margin']" position="before">
                <field name="replacement_margin"/>
            </xpath>
            <xpath expr="//field[@name='lines']//list//field[@name='margin']" position="after">
                <field name="replacement_cost_unit" optional="hide"/>
                <field name="replacement_margin" optional="hide" widget="monetary"/>
            </xpath>
        </field>
    </record>
</odoo>
```

> Verificar en `odoo-19.0/addons/point_of_sale/views/pos_order_view.xml` que el
> `<label for="margin"/>` y la lista de `lines` con `margin` estén donde se ancla (cerca
> de las líneas 96 y 142).

- [ ] **Paso 2: manifest** `'data': ['views/pos_order_views.xml'],`

- [ ] **Paso 3: actualizar y correr todos los tests de ambos módulos** → 0 fallas.

- [ ] **Paso 4: commit**

```bash
git add alpardata_pos_replacement_margin
git commit -m "feat(pos_replacement_margin): vistas de orden de POS"
```

---

### Tarea 7: READMEs y PR

- [ ] **Paso 1: `README.md` en cada módulo**: diferencia entre margen contable (AVCO) y
margen de reposición; cuándo se toma el costo (ventas: al cargar la línea y de nuevo al
confirmar; POS: al sincronizar la orden, con la fecha de la orden); fallback a AVCO;
**los pedidos y órdenes anteriores a la instalación quedan sin margen de reposición a
propósito** (recalcularlos con el costo de hoy daría un dato engañoso); dónde verlo
(pedido, orden POS, análisis de ventas y de POS como medida "Margen de reposición").

- [ ] **Paso 2: instalación sobre una base con datos** (anotar en el PR): instalar ambos
módulos en una copia con pedidos y órdenes existentes; verificar que la instalación es
rápida y que los históricos quedan con margen de reposición 0 (lo garantiza el
`pre_init_hook` de las tareas 1 y 4).

- [ ] **Paso 3: commit, push y PR contra `19.0`.**

```bash
git add alpardata_sale_replacement_margin alpardata_pos_replacement_margin
git commit -m "docs(replacement_margin): README"
git push -u origin feat/replacement-margin
```
