# Cotización Comercial — Plan de implementación

> **Para agentes:** implementar tarea por tarea, en orden. Cada paso usa checkbox (`- [ ]`).
> Si usás superpowers: REQUIRED SUB-SKILL `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`.

**Goal:** Crear `alpardata_commercial_currency_rate`: una cotización comercial (p. ej.
dólar de reposición) cargada a mano, separada de la contable, que se usa sólo para
convertir costos comerciales (referencia, reposición) y las listas de precios basadas en
ellos.

**Architecture:** El módulo base expone un hook `_convert_commercial_currency` que por
defecto usa la cotización contable. El módulo nuevo lo sobreescribe cuando la empresa
elige fuente "manual", leyendo `commercial.currency.rate`. La orden de compra no usa el
hook y sigue con la cotización contable.

**Tech Stack:** Odoo 19.0.

**Spec:** `docs/superpowers/specs/2026-09-24-commercial-currency-rate-design.md`
**Requisito previo:** punto 1 mergeado (crea `_convert_commercial_cost` en el base).

---

## Convenciones

- **Rama:** `feat/commercial-currency-rate` desde `19.0`.
- Strings y commits en castellano: `feat(commercial_currency_rate): ...`,
  `refactor(purchase_reference_cost): ...`.
- **Odoo 19:** `<list>`, `invisible="expr"`, `<chatter/>`, `<search>` sin
  `<group string>`, `models.Constraint`.
- **Semántica de `res.currency.rate` en Odoo:** `rate` = unidades de la moneda por 1
  unidad de la moneda de la empresa (1 ARS = 0,000689 USD). La cotización comercial usa
  la forma humana inversa: **pesos por 1 dólar** (1 USD = 1.450 ARS). No mezclarlas.
- **Tests:**

  ```bash
  odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_purchase_reference_cost,alpardata_commercial_currency_rate --test-enable --test-tags /alpardata_purchase_reference_cost,/alpardata_commercial_currency_rate --stop-after-init --log-level=test
  ```

## Mapa de archivos

Base (`alpardata_purchase_reference_cost/`), modificar:
- `models/product_template.py` — hook `_convert_commercial_currency` y su uso.
- `models/product_pricelist.py` — `_convert_commercial_cost` usa el hook.
- `__manifest__.py` — versión `19.0.2.3.0`.

Nuevo (`alpardata_commercial_currency_rate/`):
- `__init__.py`, `__manifest__.py`, `README.md`
- `models/__init__.py`, `models/commercial_currency_rate.py`, `models/res_company.py`,
  `models/res_config_settings.py`, `models/product_template.py`
- `security/security.xml`, `security/ir.model.access.csv`
- `views/commercial_currency_rate_views.xml`, `views/res_config_settings_views.xml`,
  `views/product_template_views.xml`, `views/menus.xml`
- `tests/__init__.py`, `tests/test_commercial_rate.py`

---

### Tarea 1: Hook en el módulo base

**Files:** Modify `alpardata_purchase_reference_cost/models/product_template.py`,
`models/product_pricelist.py`, `__manifest__.py`.

- [ ] **Paso 1: correr los tests del base** y anotar que pasan (comando de Convenciones,
sólo el base).

- [ ] **Paso 2: agregar el hook** en `product_template.py` (dentro de la clase, después de
`_get_reference_cost_seller`):

```python
    @api.model
    def _convert_commercial_currency(self, amount, from_currency, to_currency, company, date):
        """Conversión de moneda para costos comerciales (referencia/reposición y
        listas de precios basadas en ellos).

        Hook: por defecto usa la cotización contable. Módulos como la cotización
        comercial lo sobreescriben. La orden de compra NO pasa por acá.
        """
        if not from_currency or not to_currency or from_currency == to_currency:
            return amount
        return from_currency._convert(amount, to_currency, company, date, round=False)
```

- [ ] **Paso 3: usarlo en `_compute_reference_cost`**: reemplazar

```python
            company = tmpl.env.company
            seller_currency = seller.currency_id or company.currency_id
            target_currency = company.currency_id
            if seller_currency and target_currency and seller_currency != target_currency:
                cost = seller_currency._convert(
                    cost, target_currency, company, today, round=False
                )
            tmpl.reference_cost = cost
```

por

```python
            company = tmpl.env.company
            seller_currency = seller.currency_id or company.currency_id
            tmpl.reference_cost = tmpl._convert_commercial_currency(
                cost, seller_currency, company.currency_id, company, today,
            )
```

- [ ] **Paso 4: usarlo en `product_pricelist.py`**, dentro de `_convert_commercial_cost`,
reemplazar el bloque de moneda por:

```python
        src_currency = self.env.company.currency_id
        return self.env['product.template']._convert_commercial_currency(
            cost, src_currency, currency, self.env.company, date,
        )
```

(el bloque de UoM de arriba queda igual; el método termina en ese `return`).

- [ ] **Paso 5: versión** `19.0.2.3.0`.

- [ ] **Paso 6: correr los tests del base** → mismos resultados, sin tocar tests. Correr
también los de `alpardata_purchase_replacement_cost`.

- [ ] **Paso 7: commit**

```bash
git add alpardata_purchase_reference_cost
git commit -m "refactor(purchase_reference_cost): hook de conversión de moneda para costos comerciales"
```

---

### Tarea 2: Modelo de cotización comercial y conversión

**Files:** Create el esqueleto del módulo, `models/*.py`, `security/*`,
`tests/test_commercial_rate.py`.

- [ ] **Paso 1: `__init__.py`**

```python
from . import models
```

`__manifest__.py`:

```python
{
    'name': 'AlparData - Cotización Comercial',
    'version': '19.0.1.0.0',
    'summary': 'Cotización comercial (p. ej. dólar de reposición) para costos de referencia y listas de precios, separada de la contable',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Inventory/Purchase',
    'depends': ['alpardata_purchase_reference_cost', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

`models/__init__.py`:

```python
from . import commercial_currency_rate
from . import res_company
from . import res_config_settings
from . import product_template
```

`tests/__init__.py`:

```python
from . import test_commercial_rate
```

- [ ] **Paso 2: test que falla** — `tests/test_commercial_rate.py`

```python
from __future__ import annotations

from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestCommercialRate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Empresa propia en pesos: no se toca la moneda de la empresa principal
        # (Odoo no deja cambiarla si ya tiene asientos).
        cls.local = cls.env.ref('base.ARS')
        cls.usd = cls.env.ref('base.USD')
        cls.eur = cls.env.ref('base.EUR')
        (cls.local | cls.usd | cls.eur).active = True
        cls.company = cls.env['res.company'].create({
            'name': 'Comercio AR Test', 'currency_id': cls.local.id,
        })
        cls.env = cls.env(context=dict(
            cls.env.context,
            allowed_company_ids=[cls.company.id],
        ))
        today = fields.Date.today()
        # Cotización contable: 1 USD = 1000 local; 1 EUR = 1100 local
        cls.env['res.currency.rate'].create([
            {'currency_id': cls.usd.id, 'company_id': cls.company.id,
             'name': today, 'rate': 1 / 1000},
            {'currency_id': cls.eur.id, 'company_id': cls.company.id,
             'name': today, 'rate': 1 / 1100},
        ])
        cls.partner = cls.env['res.partner'].create({'name': 'Proveedor USD'})
        cls.product = cls.env['product.product'].create({'name': 'Importado'})
        cls.template = cls.product.product_tmpl_id
        cls.env['product.supplierinfo'].create({
            'partner_id': cls.partner.id,
            'product_tmpl_id': cls.template.id,
            'company_id': False,  # global: la usa también test_per_company
            'currency_id': cls.usd.id,
            'price': 2.0,
            'reference_cost': 2.0,
        })
        cls.Rate = cls.env['commercial.currency.rate']

    def _rate(self, value, currency=None, date=None):
        return self.Rate.create({
            'currency_id': (currency or self.usd).id,
            'rate': value,
            'date': date or fields.Date.today(),
        })

    def test_odoo_source_is_default(self):
        self.assertEqual(self.company.commercial_rate_source, 'odoo')
        self._rate(1450.0)
        self.assertAlmostEqual(self.template.reference_cost, 2000.0, places=2)

    def test_manual_source(self):
        self.company.commercial_rate_source = 'manual'
        self._rate(1450.0)
        self.assertAlmostEqual(self.template.reference_cost, 2900.0, places=2)

    def test_uses_latest_not_future(self):
        self.company.commercial_rate_source = 'manual'
        today = fields.Date.today()
        self._rate(1400.0, date=today - timedelta(days=3))
        self._rate(1450.0, date=today - timedelta(days=1))
        self._rate(9999.0, date=today + timedelta(days=1))
        self.assertAlmostEqual(self.template.reference_cost, 2900.0, places=2)

    def test_local_to_foreign_divides(self):
        self.company.commercial_rate_source = 'manual'
        self._rate(1450.0)
        amount = self.env['product.template']._convert_commercial_currency(
            2900.0, self.local, self.usd, self.company, fields.Date.today(),
        )
        self.assertAlmostEqual(amount, 2.0, places=6)

    def test_foreign_to_foreign(self):
        self.company.commercial_rate_source = 'manual'
        self._rate(1450.0)
        self._rate(1600.0, currency=self.eur)
        amount = self.env['product.template']._convert_commercial_currency(
            16.0, self.eur, self.usd, self.company, fields.Date.today(),
        )
        self.assertAlmostEqual(amount, 16.0 * 1600 / 1450, places=6)

    def test_missing_rate_falls_back_to_accounting(self):
        self.company.commercial_rate_source = 'manual'
        amount = self.env['product.template']._convert_commercial_currency(
            1.0, self.eur, self.local, self.company, fields.Date.today(),
        )
        self.assertAlmostEqual(amount, 1100.0, places=2)

    def test_pricelist_uses_commercial_rate(self):
        self.company.commercial_rate_source = 'manual'
        self._rate(1450.0)
        pricelist = self.env['product.pricelist'].create({
            'name': 'Lista referencia',
            'currency_id': self.local.id,
            'item_ids': [(0, 0, {
                'applied_on': '3_global', 'compute_price': 'formula',
                'base': 'reference_cost',
            })],
        })
        self.assertAlmostEqual(pricelist._get_product_price(self.product, 1.0), 2900.0, places=2)

    def test_purchase_order_keeps_accounting_rate(self):
        self.company.commercial_rate_source = 'manual'
        self._rate(1450.0)
        po = self.env['purchase.order'].create({
            'partner_id': self.partner.id, 'currency_id': self.local.id,
        })
        line = self.env['purchase.order.line'].create({
            'order_id': po.id, 'product_id': self.product.id, 'product_qty': 1.0,
        })
        self.assertAlmostEqual(line.price_unit, 2000.0, places=2)

    def test_rate_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._rate(0.0)

    def test_unique_per_day(self):
        self._rate(1450.0)
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            self._rate(1460.0)
            self.env.flush_all()

    def test_not_company_currency(self):
        with self.assertRaises(ValidationError):
            self._rate(1.0, currency=self.local)

    def test_per_company(self):
        other = self.env['res.company'].create({
            'name': 'Otra', 'currency_id': self.local.id,
            'commercial_rate_source': 'manual',
        })
        env = self.env(context=dict(
            self.env.context, allowed_company_ids=[self.company.id, other.id],
        ))
        self.company.commercial_rate_source = 'manual'
        self._rate(1450.0)
        env['commercial.currency.rate'].create({
            'currency_id': self.usd.id, 'rate': 1500.0, 'company_id': other.id,
        })
        template = self.template.with_env(env)
        self.assertAlmostEqual(template.with_company(other).reference_cost, 3000.0, places=2)
        self.assertAlmostEqual(template.with_company(self.company).reference_cost, 2900.0, places=2)
```

- [ ] **Paso 3: correr** → falla.

- [ ] **Paso 4: `models/commercial_currency_rate.py`**

```python
from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CommercialCurrencyRate(models.Model):
    _name = 'commercial.currency.rate'
    _description = 'Cotización comercial'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _rec_name = 'currency_id'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True, index=True,
        default=lambda self: self.env.company,
    )
    company_currency_id = fields.Many2one(related='company_id.currency_id')
    currency_id = fields.Many2one('res.currency', string='Moneda', required=True, index=True)
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today, index=True)
    rate = fields.Float(
        string='Cotización', digits=(16, 4), required=True, tracking=True,
        help='Pesos (moneda de la empresa) por 1 unidad de la moneda. Ej.: 1 USD = 1.450.',
    )
    note = fields.Char(string='Nota', help='Ej.: MEP cierre, BNA vendedor + 2 %.')
    is_stale = fields.Boolean(string='Desactualizada', compute='_compute_is_stale')

    _company_currency_date_uniq = models.Constraint(
        'UNIQUE(company_id, currency_id, date)',
        'Ya hay una cotización comercial para esa moneda y fecha.',
    )

    @api.constrains('rate')
    def _check_rate(self) -> None:
        for rec in self:
            if rec.rate <= 0:
                raise ValidationError('La cotización debe ser mayor que cero.')

    @api.constrains('currency_id', 'company_id')
    def _check_currency(self) -> None:
        for rec in self:
            if rec.currency_id == rec.company_id.currency_id:
                raise ValidationError(
                    'La moneda de la cotización no puede ser la moneda de la empresa.'
                )

    @api.depends('date', 'company_id.commercial_rate_max_age_days')
    def _compute_is_stale(self) -> None:
        """Sólo la cotización más nueva de cada moneda puede estar desactualizada."""
        today = fields.Date.context_today(self)
        for rec in self:
            newest = self.search([
                ('company_id', '=', rec.company_id.id),
                ('currency_id', '=', rec.currency_id.id),
            ], limit=1)
            rec.is_stale = (
                rec == newest
                and (today - rec.date).days > rec.company_id.commercial_rate_max_age_days
            )

    @api.model
    def _get_rate(self, currency, company, date) -> float:
        """Pesos por 1 unidad de `currency` vigente a `date`. 0.0 si no hay."""
        rec = self.sudo().search([
            ('company_id', '=', company.id),
            ('currency_id', '=', currency.id),
            ('date', '<=', date),
        ], limit=1)
        return rec.rate
```

- [ ] **Paso 5: `models/res_company.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    commercial_rate_source = fields.Selection(
        [('odoo', 'Cotización contable de Odoo'), ('manual', 'Cotización comercial manual')],
        string='Cotización para costos comerciales', default='odoo', required=True,
    )
    commercial_rate_max_age_days = fields.Integer(
        string='Antigüedad máxima (días)', default=7,
        help='Las cotizaciones más viejas se marcan como desactualizadas.',
    )
```

- [ ] **Paso 6: `models/res_config_settings.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    commercial_rate_source = fields.Selection(
        related='company_id.commercial_rate_source', readonly=False,
    )
    commercial_rate_max_age_days = fields.Integer(
        related='company_id.commercial_rate_max_age_days', readonly=False,
    )
```

- [ ] **Paso 7: `models/product_template.py`** (override del hook + texto informativo)

```python
from __future__ import annotations

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    reference_cost_rate_info = fields.Char(
        string='Cotización aplicada', compute='_compute_reference_cost_rate_info',
    )

    @api.model
    def _convert_commercial_currency(self, amount, from_currency, to_currency, company, date):
        if (
            company.commercial_rate_source != 'manual'
            or not from_currency or not to_currency or from_currency == to_currency
        ):
            return super()._convert_commercial_currency(
                amount, from_currency, to_currency, company, date,
            )
        local = company.currency_id
        Rate = self.env['commercial.currency.rate']
        # 1) a moneda de la empresa
        if from_currency == local:
            local_amount = amount
        else:
            rate = Rate._get_rate(from_currency, company, date)
            if not rate:
                _logger.warning(
                    'Sin cotización comercial de %s para %s al %s: se usa la contable.',
                    from_currency.name, company.name, date,
                )
                local_amount = super()._convert_commercial_currency(
                    amount, from_currency, local, company, date,
                )
            else:
                local_amount = amount * rate
        # 2) de moneda de la empresa a destino
        if to_currency == local:
            return local_amount
        rate = Rate._get_rate(to_currency, company, date)
        if not rate:
            _logger.warning(
                'Sin cotización comercial de %s para %s al %s: se usa la contable.',
                to_currency.name, company.name, date,
            )
            return super()._convert_commercial_currency(
                local_amount, local, to_currency, company, date,
            )
        return local_amount / rate

    @api.depends_context('company')
    def _compute_reference_cost_rate_info(self) -> None:
        today = fields.Date.context_today(self)
        company = self.env.company
        for tmpl in self:
            seller = tmpl._get_reference_cost_seller()
            currency = seller.currency_id if seller else False
            if not currency or currency == company.currency_id:
                tmpl.reference_cost_rate_info = False
                continue
            rate = 0.0
            if company.commercial_rate_source == 'manual':
                rate = self.env['commercial.currency.rate']._get_rate(currency, company, today)
            if rate:
                source = 'comercial'
            else:
                rate = currency._convert(1.0, company.currency_id, company, today, round=False)
                source = 'contable'
            tmpl.reference_cost_rate_info = (
                f'{currency.name} 1 = {company.currency_id.symbol} '
                f'{rate:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
                + f' ({source}, {today.strftime("%d/%m/%Y")})'
            )
```

- [ ] **Paso 8: seguridad** — `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_commercial_rate_user,commercial.currency.rate.user,model_commercial_currency_rate,purchase.group_purchase_user,1,0,0,0
access_commercial_rate_manager,commercial.currency.rate.manager,model_commercial_currency_rate,purchase.group_purchase_manager,1,1,1,1
```

`security/security.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="rule_commercial_rate_company" model="ir.rule">
        <field name="name">Cotización comercial: multi-empresa</field>
        <field name="model_id" ref="model_commercial_currency_rate"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    </record>
</odoo>
```

> `_get_rate` usa `sudo()` porque el cálculo de costos lo dispara cualquier usuario que
> vea un producto o una lista de precios, no sólo compras.

- [ ] **Paso 9: correr tests** → pasan.

- [ ] **Paso 10: commit**

```bash
git add alpardata_commercial_currency_rate
git commit -m "feat(commercial_currency_rate): cotización comercial para costos y listas de precios"
```

---

### Tarea 3: Vistas y menús

**Files:** Create las 4 vistas; Modify manifest.

- [ ] **Paso 1: `views/commercial_currency_rate_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="commercial_currency_rate_view_list" model="ir.ui.view">
        <field name="name">commercial.currency.rate.list</field>
        <field name="model">commercial.currency.rate</field>
        <field name="arch" type="xml">
            <list editable="top" decoration-danger="is_stale">
                <field name="date"/>
                <field name="currency_id"/>
                <field name="rate"/>
                <field name="note"/>
                <field name="is_stale" optional="show"/>
                <field name="company_id" groups="base.group_multi_company"/>
            </list>
        </field>
    </record>

    <record id="commercial_currency_rate_view_search" model="ir.ui.view">
        <field name="name">commercial.currency.rate.search</field>
        <field name="model">commercial.currency.rate</field>
        <field name="arch" type="xml">
            <search>
                <field name="currency_id"/>
                <group>
                    <filter name="group_currency" string="Moneda" context="{'group_by': 'currency_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_commercial_currency_rate" model="ir.actions.act_window">
        <field name="name">Cotizaciones comerciales</field>
        <field name="res_model">commercial.currency.rate</field>
        <field name="view_mode">list</field>
        <field name="context">{'search_default_group_currency': 1}</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Cargá la cotización comercial del día</p>
            <p>Se usa para convertir costos de referencia y reposición en moneda extranjera
               cuando en Ajustes se elige "Cotización comercial manual".</p>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 2: `views/res_config_settings_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="res_config_settings_view_form_commercial_rate" model="ir.ui.view">
        <field name="name">res.config.settings.form.commercial.rate</field>
        <field name="model">res.config.settings</field>
        <field name="inherit_id" ref="alpardata_purchase_reference_cost.res_config_settings_view_form_reference_cost"/>
        <field name="arch" type="xml">
            <xpath expr="//block[@name='reference_cost_settings']" position="inside">
                <setting string="Cotización para costos comerciales"
                         help="Cotización con la que se convierten a pesos los costos de proveedores en moneda extranjera. No afecta órdenes de compra ni contabilidad.">
                    <field name="commercial_rate_source" widget="radio"/>
                    <div class="mt8" invisible="commercial_rate_source != 'manual'">
                        <label for="commercial_rate_max_age_days" class="o_light_label"/>
                        <field name="commercial_rate_max_age_days" class="oe_inline"/>
                    </div>
                </setting>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 3: `views/product_template_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_product_template_form_rate_info" model="ir.ui.view">
        <field name="name">product.template.form.rate.info</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="alpardata_purchase_reference_cost.view_product_template_form_reference_cost"/>
        <field name="arch" type="xml">
            <xpath expr="//page[@name='reference_cost_tab']//field[@name='reference_cost']" position="after">
                <field name="reference_cost_rate_info" invisible="not reference_cost_rate_info"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 4: `views/menus.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_commercial_currency_rate"
              name="Cotizaciones comerciales"
              parent="purchase.menu_purchase_config"
              action="action_commercial_currency_rate"
              sequence="45"/>
</odoo>
```

- [ ] **Paso 5: manifest `data`**:

```python
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/commercial_currency_rate_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_template_views.xml',
        'views/menus.xml',
    ],
```

- [ ] **Paso 6: actualizar y correr todos los tests** → 0 fallas.

- [ ] **Paso 7: prueba manual** (anotar en el PR): fuente manual, cargar USD 1.450,
producto con proveedor en USD → la ficha muestra "USD 1 = $ 1.450,00 (comercial, ...)" y
el costo convertido; una OC en pesos del mismo producto sigue con la cotización contable.

- [ ] **Paso 8: commit**

```bash
git add alpardata_commercial_currency_rate
git commit -m "feat(commercial_currency_rate): vistas, ajustes y menú"
```

---

### Tarea 4: README y PR

- [ ] **Paso 1: `README.md`**: diferencia entre cotización contable y comercial, cómo
cargarla (pesos por unidad), qué convierte (costo de referencia, reposición, listas de
precios con esas bases) y qué no (OC, facturas, contabilidad), fallback a la contable si
falta la cotización, relación con las etiquetas pendientes (el cron del módulo de
etiquetas detecta los precios que cambian por una cotización nueva).
- [ ] **Paso 2: commit, push y PR contra `19.0`.**

```bash
git add alpardata_commercial_currency_rate/README.md
git commit -m "docs(commercial_currency_rate): README"
git push -u origin feat/commercial-currency-rate
```
