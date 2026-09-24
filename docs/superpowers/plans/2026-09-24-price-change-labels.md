# Margen Erosionado y Etiquetas Pendientes — Plan de implementación

> **Para agentes:** implementar tarea por tarea, en orden. Cada paso usa checkbox (`- [ ]`).
> Si usás superpowers: REQUIRED SUB-SKILL `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`.

**Goal:** Crear `alpardata_price_change_labels`: detectar productos con recargo sobre
reposición por debajo del objetivo y mantener una cola de etiquetas de góndola pendientes
de reimprimir cuando el precio cambió.

**Architecture:** Un modelo `product.price.watch` (una fila por producto y empresa)
guarda la foto del precio de góndola, la reposición y el último precio impreso. Un
proceso de refresco (cron diario + botón) actualiza las fotos usando **la misma función
que imprime la etiqueta 3x8** (`_get_label_info`). Imprimir etiquetas 3x8 regulares
registra el precio impreso.

**Tech Stack:** Odoo 19.0.

**Spec:** `docs/superpowers/specs/2026-09-24-price-change-labels-design.md`
**Requisitos previos:** punto 1 (`alpardata_purchase_replacement_cost`) mergeado;
`product_label_3x8` en el repo (ya existe).

---

## Convenciones

- **Rama:** `feat/price-change-labels` desde `19.0`.
- Strings y commits en castellano: `feat(price_change_labels): ...`.
- **Odoo 19:** `<list>`, `invisible="expr"`, `<chatter/>`, `<search>` sin
  `<group string>`, `models.Constraint` para restricciones SQL.
- Fuente de Odoo: `C:\Users\Santiago\Desktop\Odoo\odoo-19.0`.
- **Tests:**

  ```bash
  odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_price_change_labels --test-enable --test-tags /alpardata_price_change_labels --stop-after-init --log-level=test
  ```

  Sin instancia: `python -m py_compile` + parseo XML con lxml; commit con
  `[tests no ejecutados]`.

## Mapa de archivos (nuevo, bajo `alpardata_price_change_labels/`)

- `__init__.py` (incluye `post_init_hook`), `__manifest__.py`, `README.md`
- `models/__init__.py`
- `models/res_company.py`, `models/res_config_settings.py`
- `models/product_category.py`, `models/product_template.py` — recargo objetivo
- `models/product_price_watch.py` — fotos, refresco, cron, impresión
- `wizard/__init__.py`, `wizard/product_label_layout.py` — registrar impresión y aviso
- `data/ir_cron.xml`
- `security/security.xml`, `security/ir.model.access.csv`
- `views/product_price_watch_views.xml`, `views/product_category_views.xml`,
  `views/product_template_views.xml`, `views/res_config_settings_views.xml`,
  `views/product_label_layout_views.xml`, `views/menus.xml`
- `tests/__init__.py`, `tests/common.py`, `tests/test_markup.py`,
  `tests/test_label_queue.py`, `tests/test_suggested_price.py`

---

### Tarea 1: Esqueleto, empresa, ajustes y recargo objetivo

**Files:** Create `__init__.py`, `__manifest__.py`, `models/__init__.py`,
`models/res_company.py`, `models/res_config_settings.py`, `models/product_category.py`,
`models/product_template.py`, `wizard/__init__.py`, `tests/__init__.py`,
`tests/common.py`, `tests/test_markup.py` (parcial).

- [ ] **Paso 1: `__init__.py`**

```python
from . import models
from . import wizard


def post_init_hook(env):
    """Al instalar, toma la foto de precios y la marca como impresa para que no
    queden todos los productos como etiqueta pendiente."""
    watch = env['product.price.watch'].sudo()
    for company in env['res.company'].search([]):
        watches = watch._refresh_company(company)
        for rec in watches:
            rec.label_printed_price = rec.shelf_price
```

- [ ] **Paso 2: `__manifest__.py`**

```python
{
    'name': 'AlparData - Margen Erosionado y Etiquetas Pendientes',
    'version': '19.0.1.0.0',
    'summary': 'Alerta de recargo bajo objetivo sobre costo de reposición y cola de etiquetas de góndola a reimprimir',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Inventory/Purchase',
    'depends': ['alpardata_purchase_replacement_cost', 'product_label_3x8'],
    'data': [],  # la tarea 4 agrega seguridad, cron y vistas
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

> `post_init_hook` usa `product.price.watch`, que se crea en la tarea 2. Hasta entonces
> el módulo no se instala limpio: está bien, se prueba a partir de la tarea 2.

- [ ] **Paso 3: `models/__init__.py`**

```python
from . import res_company
from . import res_config_settings
from . import product_category
from . import product_template
# from . import product_price_watch
```

`wizard/__init__.py`:

```python
# from . import product_label_layout
```

`tests/__init__.py`:

```python
from . import test_markup
# from . import test_label_queue
```

- [ ] **Paso 4: `models/res_company.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    shelf_pricelist_id = fields.Many2one(
        'product.pricelist', string='Lista de góndola',
        help='Lista con la que se imprimen las etiquetas de góndola. Vacía: precio de venta.',
    )
    markup_tolerance_pct = fields.Float(
        string='Tolerancia de recargo (puntos)', default=2.0,
        help='Se alerta cuando el recargo actual queda por debajo del objetivo menos esta tolerancia.',
    )
```

- [ ] **Paso 5: `models/res_config_settings.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    shelf_pricelist_id = fields.Many2one(
        related='company_id.shelf_pricelist_id', readonly=False,
    )
    markup_tolerance_pct = fields.Float(
        related='company_id.markup_tolerance_pct', readonly=False,
    )
```

- [ ] **Paso 6: `models/product_category.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    # 'commercial.conditions.access.mixin' ya está en product.category (punto 1):
    # alcanza con sumar el campo a los protegidos.
    _commercial_condition_fields = ('internal_tax_pct', 'target_markup_pct')

    target_markup_pct = fields.Float(
        string='Recargo objetivo (%)',
        help='Recargo esperado sobre el costo de reposición (precio sin impuestos / reposición − 1).',
    )
```

- [ ] **Paso 7: `models/product_template.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    _commercial_condition_fields = ('internal_tax_pct', 'target_markup_pct')

    target_markup_pct = fields.Float(
        string='Recargo objetivo (%)',
        compute='_compute_target_markup_pct',
        store=True,
        readonly=False,
        precompute=True,
        help='Se toma de la categoría; se puede modificar a mano.',
    )

    @api.depends('categ_id')
    def _compute_target_markup_pct(self) -> None:
        for tmpl in self:
            tmpl.target_markup_pct = tmpl.categ_id.target_markup_pct
```

> `_commercial_condition_fields` pisa la tupla del punto 1: por eso se repite
> `internal_tax_pct`. Si el punto 1 agregara campos protegidos nuevos, hay que sumarlos acá.

- [ ] **Paso 8: `tests/common.py`**

```python
from __future__ import annotations

from odoo.tests.common import TransactionCase


class PriceWatchCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Proveedor Góndola'})
        cls.categ = cls.env['product.category'].create({
            'name': 'Almacén Test', 'target_markup_pct': 40.0,
        })
        cls.tax = cls.env['account.tax'].create({
            'name': 'IVA 21 incluido test',
            'amount': 21.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'price_include_override': 'tax_included',
            'company_id': cls.company.id,
        })
        cls.template = cls.env['product.template'].create({
            'name': 'Fideos 500g',
            'categ_id': cls.categ.id,
            'list_price': 1694.0,  # 1400 sin IVA
            'taxes_id': [(6, 0, cls.tax.ids)],
            'sale_ok': True,
        })
        cls.seller = cls.env['product.supplierinfo'].create({
            'partner_id': cls.partner.id,
            'product_tmpl_id': cls.template.id,
            'price': 1000.0,
            'reference_cost': 1000.0,
        })
        cls.watch_model = cls.env['product.price.watch']

    def _watch(self, template=None):
        return self.watch_model._refresh(template or self.template, self.company)
```

> El campo que marca un impuesto como "precio incluido" en 19 es `price_include_override`
> (`'tax_included'`). Verificar en `odoo-19.0/addons/account/models/account_tax.py`; si
> es otro, ajustar. El resultado esperado del test depende de que `_get_label_info`
> calcule el neto dividiendo por 1,21.

- [ ] **Paso 9: `tests/test_markup.py`** (parte de recargo objetivo; lo demás en tarea 2)

```python
from __future__ import annotations

from odoo.tests import tagged

from .common import PriceWatchCommon


@tagged('post_install', '-at_install')
class TestTargetMarkup(PriceWatchCommon):

    def test_target_from_category(self):
        self.assertEqual(self.template.target_markup_pct, 40.0)

    def test_target_manual_override(self):
        self.template.target_markup_pct = 30.0
        self.assertEqual(self.template.target_markup_pct, 30.0)
```

- [ ] **Paso 10:** no correr todavía (falta el modelo del hook). Commit:

```bash
git add alpardata_price_change_labels
git commit -m "feat(price_change_labels): esqueleto, lista de góndola y recargo objetivo"
```

---

### Tarea 2: Modelo `product.price.watch` y refresco

**Files:** Create `models/product_price_watch.py`; Modify `tests/test_markup.py`.

- [ ] **Paso 1: agregar tests** al final de `tests/test_markup.py`:

```python
@tagged('post_install', '-at_install')
class TestPriceWatchRefresh(PriceWatchCommon):

    def test_refresh_values(self):
        watch = self._watch()
        self.assertEqual(len(watch), 1)
        self.assertAlmostEqual(watch.shelf_price, 1694.0, places=2)
        self.assertAlmostEqual(watch.shelf_price_untaxed, 1400.0, places=2)
        self.assertAlmostEqual(watch.replacement_cost, 1000.0, places=2)
        self.assertAlmostEqual(watch.markup_pct, 40.0, places=2)
        self.assertEqual(watch.markup_alert, 'ok')

    def test_refresh_is_idempotent(self):
        first = self._watch()
        second = self._watch()
        self.assertEqual(first, second)

    def test_markup_below_target(self):
        self.seller.reference_cost = 1100.0  # recargo 27,27 %
        watch = self._watch()
        self.assertEqual(watch.markup_alert, 'below')

    def test_tolerance(self):
        self.seller.reference_cost = 1010.0  # recargo 38,6 %: dentro de 2 puntos
        self.assertEqual(self._watch().markup_alert, 'ok')

    def test_no_cost(self):
        template = self.env['product.template'].create({'name': 'Sin proveedor', 'sale_ok': True})
        self.assertEqual(self._watch(template).markup_alert, 'no_cost')

    def test_shelf_pricelist(self):
        pricelist = self.env['product.pricelist'].create({
            'name': 'Góndola test',
            'item_ids': [(0, 0, {
                'applied_on': '3_global',
                'compute_price': 'fixed',
                'fixed_price': 2000.0,
            })],
        })
        self.company.shelf_pricelist_id = pricelist
        self.assertAlmostEqual(self._watch().shelf_price, 2000.0, places=2)

    def test_per_company(self):
        other = self.env['res.company'].create({'name': 'Sucursal Góndola'})
        mine = self._watch()
        theirs = self.watch_model._refresh(self.template, other)
        self.assertNotEqual(mine, theirs)
        self.assertEqual(theirs.company_id, other)
```

- [ ] **Paso 2: `models/product_price_watch.py`**

```python
from __future__ import annotations

import logging
import threading

from odoo import _, api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

LABEL_REPORT = 'report.product_label_3x8.report_producttemplatelabel3x8'
BATCH_SIZE = 1000


class ProductPriceWatch(models.Model):
    _name = 'product.price.watch'
    _description = 'Control de precio de góndola'
    _order = 'label_pending desc, product_tmpl_id'
    _rec_name = 'product_tmpl_id'
    _check_company_auto = True

    product_tmpl_id = fields.Many2one(
        'product.template', string='Producto', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one('res.company', string='Empresa', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    categ_id = fields.Many2one(related='product_tmpl_id.categ_id', store=True, string='Categoría')
    shelf_price = fields.Monetary(string='Precio de góndola')
    shelf_price_untaxed = fields.Monetary(string='Precio sin impuestos')
    replacement_cost = fields.Monetary(string='Costo de reposición')
    target_markup_pct = fields.Float(
        related='product_tmpl_id.target_markup_pct', string='Recargo objetivo (%)',
    )
    markup_pct = fields.Float(
        string='Recargo actual (%)', compute='_compute_markup', store=True, digits=(16, 2),
    )
    markup_alert = fields.Selection(
        [('ok', 'OK'), ('below', 'Bajo objetivo'), ('no_cost', 'Sin costo')],
        string='Margen', compute='_compute_markup', store=True, index=True,
    )
    label_printed_price = fields.Monetary(string='Precio impreso')
    label_printed_date = fields.Datetime(string='Impresa el')
    label_variation_pct = fields.Float(
        string='Variación (%)', compute='_compute_label_pending', store=True, digits=(16, 2),
    )
    label_pending = fields.Boolean(
        string='Etiqueta pendiente', compute='_compute_label_pending', store=True, index=True,
    )
    refreshed_at = fields.Datetime(string='Actualizado')

    _product_company_uniq = models.Constraint(
        'UNIQUE(product_tmpl_id, company_id)',
        'Ya existe un control de precio para ese producto y empresa.',
    )

    # ── Computes ──────────────────────────────────────────────────────────────
    @api.depends('shelf_price_untaxed', 'replacement_cost',
                 'product_tmpl_id.target_markup_pct', 'company_id.markup_tolerance_pct')
    def _compute_markup(self) -> None:
        for rec in self:
            if not rec.replacement_cost:
                rec.markup_pct = 0.0
                rec.markup_alert = 'no_cost'
                continue
            rec.markup_pct = (rec.shelf_price_untaxed / rec.replacement_cost - 1) * 100
            floor = rec.target_markup_pct - rec.company_id.markup_tolerance_pct
            rec.markup_alert = 'below' if rec.markup_pct < floor else 'ok'

    @api.depends('shelf_price', 'label_printed_price')
    def _compute_label_pending(self) -> None:
        for rec in self:
            rec.label_pending = float_compare(
                rec.shelf_price, rec.label_printed_price, precision_digits=2,
            ) != 0
            rec.label_variation_pct = (
                (rec.shelf_price / rec.label_printed_price - 1) * 100
                if rec.label_printed_price else 0.0
            )

    # ── Refresco ──────────────────────────────────────────────────────────────
    @api.model
    def _label_price(self, template, company, pricelist):
        """(precio final, precio sin impuestos) tal como los imprime la etiqueta 3x8."""
        report = self.env[LABEL_REPORT].with_company(company)
        info = report._get_label_info(template.with_company(company), pricelist=pricelist or None)
        return info['price_final'], info['price_net']

    @api.model
    def _refresh(self, templates, company):
        """Crea o actualiza las filas de `templates` para `company`. Devuelve las filas."""
        self = self.sudo()
        existing = self.search([
            ('product_tmpl_id', 'in', templates.ids), ('company_id', '=', company.id),
        ])
        by_template = {rec.product_tmpl_id.id: rec for rec in existing}
        pricelist = company.shelf_pricelist_id
        now = fields.Datetime.now()
        to_create = []
        for template in templates:
            price, untaxed = self._label_price(template, company, pricelist)
            vals = {
                'shelf_price': price,
                'shelf_price_untaxed': untaxed,
                'replacement_cost': template.with_company(company).replacement_cost,
                'refreshed_at': now,
            }
            rec = by_template.get(template.id)
            if rec:
                rec.write(vals)
            else:
                to_create.append({
                    **vals,
                    'product_tmpl_id': template.id,
                    'company_id': company.id,
                    'label_printed_price': 0.0,
                })
        created = self.create(to_create) if to_create else self.browse()
        return existing | created

    @api.model
    def _templates_for_company(self, company):
        return self.env['product.template'].search([
            ('sale_ok', '=', True),
            ('company_id', 'in', [company.id, False]),
        ])

    @api.model
    def _refresh_company(self, company):
        templates = self._templates_for_company(company)
        result = self.browse()
        testing = getattr(threading.current_thread(), 'testing', False)
        for start in range(0, len(templates), BATCH_SIZE):
            result |= self._refresh(templates[start:start + BATCH_SIZE], company)
            if not testing:
                self.env.cr.commit()
        return result

    @api.model
    def _cron_refresh(self) -> None:
        for company in self.env['res.company'].search([]):
            _logger.info('Control de precios de góndola: empresa %s', company.name)
            self._refresh_company(company)

    def action_refresh(self) -> None:
        for company in self.company_id:
            recs = self.filtered(lambda r: r.company_id == company)
            self._refresh(recs.product_tmpl_id, company)

    # ── Impresión ─────────────────────────────────────────────────────────────
    @api.model
    def _mark_printed(self, templates, company, pricelist):
        """Registra el precio impreso con `pricelist` (la del wizard)."""
        watches = self._refresh(templates, company)
        now = fields.Datetime.now()
        for rec in watches:
            price, _untaxed = self._label_price(rec.product_tmpl_id, company, pricelist)
            rec.write({'label_printed_price': price, 'label_printed_date': now})
        return watches

    def action_print_labels(self) -> dict:
        company = self.company_id[:1] or self.env.company
        return {
            'type': 'ir.actions.act_window',
            'name': _('Imprimir etiquetas'),
            'res_model': 'product.label.layout',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_product_tmpl_ids': self.product_tmpl_id.ids,
                'default_print_format': '3x8xprice',
                'default_pricelist_id': company.shelf_pricelist_id.id,
            },
        }
```

> `_get_label_info` está en `product_label_3x8/report/product_label_report.py`; con
> `is_promo=False` devuelve el precio regular. Si su firma cambió, adaptar `_label_price`
> y nada más.

- [ ] **Paso 3: descomentar** `product_price_watch` en `models/__init__.py`. Agregar ACL
mínima para que los tests carguen — `security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_price_watch_user,product.price.watch.user,model_product_price_watch,base.group_user,1,0,0,0
access_price_watch_manager,product.price.watch.manager,model_product_price_watch,purchase.group_purchase_manager,1,1,1,1
```

y en el manifest `'data': ['security/ir.model.access.csv'],`.

- [ ] **Paso 4: correr tests** → `TestTargetMarkup` y `TestPriceWatchRefresh` pasan.

- [ ] **Paso 5: commit**

```bash
git add alpardata_price_change_labels
git commit -m "feat(price_change_labels): control de precio de góndola y recargo sobre reposición"
```

---

### Tarea 3: Cola de etiquetas (impresión y hook de instalación)

**Files:** Create `wizard/product_label_layout.py`, `tests/test_label_queue.py`.

- [ ] **Paso 1: test que falla** — `tests/test_label_queue.py`

```python
from __future__ import annotations

from odoo.tests import tagged

from odoo.addons.alpardata_price_change_labels import post_init_hook

from .common import PriceWatchCommon


@tagged('post_install', '-at_install')
class TestLabelQueue(PriceWatchCommon):

    def _print(self, fmt='3x8xprice', pricelist=None):
        wizard = self.env['product.label.layout'].create({
            'product_tmpl_ids': [(6, 0, self.template.ids)],
            'print_format': fmt,
            'pricelist_id': pricelist.id if pricelist else False,
        })
        wizard.process()

    def test_new_product_is_pending(self):
        self.assertTrue(self._watch().label_pending)

    def test_print_clears_pending(self):
        self._watch()
        self._print()
        watch = self._watch()
        self.assertFalse(watch.label_pending)
        self.assertAlmostEqual(watch.label_printed_price, 1694.0, places=2)
        self.assertTrue(watch.label_printed_date)

    def test_price_change_makes_pending(self):
        self._print()
        self.template.list_price = 1800.0
        watch = self._watch()
        self.assertTrue(watch.label_pending)
        self.assertAlmostEqual(watch.label_variation_pct, (1800 / 1694 - 1) * 100, places=2)

    def test_promo_does_not_clear(self):
        self._watch()
        self._print(fmt='3x8xpromo')
        self.assertTrue(self._watch().label_pending)

    def test_other_pricelist_keeps_pending(self):
        other = self.env['product.pricelist'].create({
            'name': 'Mayorista test',
            'item_ids': [(0, 0, {
                'applied_on': '3_global', 'compute_price': 'fixed', 'fixed_price': 1500.0,
            })],
        })
        self._print(pricelist=other)
        self.assertTrue(self._watch().label_pending)

    def test_post_init_hook_leaves_nothing_pending(self):
        post_init_hook(self.env)
        pending = self.watch_model.search([
            ('company_id', '=', self.company.id), ('label_pending', '=', True),
        ])
        self.assertFalse(pending)

    def test_cost_change_with_replacement_pricelist(self):
        """Regla con base reposición: sube el costo → sube el precio → etiqueta pendiente."""
        pricelist = self.env['product.pricelist'].create({
            'name': 'Góndola reposición',
            'item_ids': [(0, 0, {
                'applied_on': '3_global', 'compute_price': 'formula',
                'base': 'replacement_cost', 'price_markup': 69.4,
            })],
        })
        self.company.shelf_pricelist_id = pricelist
        self._print(pricelist=pricelist)
        self.assertFalse(self._watch().label_pending)
        self.seller.reference_cost = 1100.0
        self.assertTrue(self._watch().label_pending)
```

- [ ] **Paso 2: `wizard/product_label_layout.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    shelf_pricelist_warning = fields.Char(compute='_compute_shelf_pricelist_warning')

    @api.depends('pricelist_id', 'print_format')
    def _compute_shelf_pricelist_warning(self) -> None:
        shelf = self.env.company.shelf_pricelist_id
        for wizard in self:
            if wizard.print_format == '3x8xprice' and wizard.pricelist_id != shelf:
                wizard.shelf_pricelist_warning = (
                    f'La lista elegida no es la lista de góndola '
                    f'({shelf.display_name or "precio de venta"}): los productos '
                    f'seguirán como etiqueta pendiente.'
                )
            else:
                wizard.shelf_pricelist_warning = False

    def process(self):
        action = super().process()
        if self.print_format == '3x8xprice':
            templates = self.product_tmpl_ids or self.product_ids.product_tmpl_id
            self.env['product.price.watch'].sudo()._mark_printed(
                templates, self.env.company, self.pricelist_id,
            )
        return action
```

- [ ] **Paso 3: descomentar** `product_label_layout` en `wizard/__init__.py` y
`test_label_queue` en `tests/__init__.py`.

- [ ] **Paso 4: correr tests** → pasan. Si `process()` falla en el test por el renderizado
del PDF (wkhtmltopdf ausente), no importa: `process()` sólo devuelve la acción del
reporte, no renderiza. Si igual renderizara, parchear en el test
`self.patch(type(self.env['ir.actions.report']), 'report_action', lambda *a, **k: {})`.

- [ ] **Paso 5: commit**

```bash
git add alpardata_price_change_labels
git commit -m "feat(price_change_labels): cola de etiquetas pendientes al imprimir 3x8"
```

---

### Tarea 4: Seguridad, cron, vistas y menús

**Files:** Create `security/security.xml`, `data/ir_cron.xml`, las vistas.

- [ ] **Paso 1: `security/security.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="rule_price_watch_company" model="ir.rule">
        <field name="name">Control de precio de góndola: multi-empresa</field>
        <field name="model_id" ref="model_product_price_watch"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    </record>
</odoo>
```

- [ ] **Paso 2: `data/ir_cron.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="ir_cron_price_watch_refresh" model="ir.cron">
        <field name="name">Góndola: actualizar precios y etiquetas pendientes</field>
        <field name="model_id" ref="model_product_price_watch"/>
        <field name="state">code</field>
        <field name="code">model._cron_refresh()</field>
        <field name="interval_number">1</field>
        <field name="interval_type">days</field>
        <field name="active" eval="True"/>
    </record>
</odoo>
```

- [ ] **Paso 3: `views/product_price_watch_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_price_watch_view_list_labels" model="ir.ui.view">
        <field name="name">product.price.watch.list.labels</field>
        <field name="model">product.price.watch</field>
        <field name="arch" type="xml">
            <list create="0" edit="0" delete="0">
                <header>
                    <button name="action_print_labels" type="object" string="Imprimir etiquetas"
                            class="btn-primary"/>
                    <button name="action_refresh" type="object" string="Actualizar"/>
                </header>
                <field name="product_tmpl_id"/>
                <field name="categ_id" optional="show"/>
                <field name="currency_id" column_invisible="1"/>
                <field name="label_printed_price"/>
                <field name="shelf_price"/>
                <field name="label_variation_pct"
                       decoration-danger="label_variation_pct &gt; 0"
                       decoration-success="label_variation_pct &lt; 0"/>
                <field name="label_printed_date" optional="show"/>
                <field name="refreshed_at" optional="hide"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="product_price_watch_view_list_markup" model="ir.ui.view">
        <field name="name">product.price.watch.list.markup</field>
        <field name="model">product.price.watch</field>
        <field name="priority">20</field>
        <field name="arch" type="xml">
            <list create="0" edit="0" delete="0">
                <header>
                    <button name="action_refresh" type="object" string="Actualizar"/>
                </header>
                <field name="product_tmpl_id"/>
                <field name="categ_id" optional="show"/>
                <field name="currency_id" column_invisible="1"/>
                <field name="replacement_cost"/>
                <field name="shelf_price_untaxed"/>
                <field name="markup_pct"/>
                <field name="target_markup_pct"/>
                <field name="markup_alert" widget="badge"
                       decoration-success="markup_alert == 'ok'"
                       decoration-danger="markup_alert == 'below'"
                       decoration-muted="markup_alert == 'no_cost'"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="product_price_watch_view_search" model="ir.ui.view">
        <field name="name">product.price.watch.search</field>
        <field name="model">product.price.watch</field>
        <field name="arch" type="xml">
            <search>
                <field name="product_tmpl_id"/>
                <field name="categ_id"/>
                <filter name="filter_label_pending" string="Etiqueta pendiente"
                        domain="[('label_pending', '=', True)]"/>
                <filter name="filter_below" string="Margen bajo objetivo"
                        domain="[('markup_alert', '=', 'below')]"/>
                <group>
                    <filter name="group_categ" string="Categoría" context="{'group_by': 'categ_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_price_watch_labels" model="ir.actions.act_window">
        <field name="name">Etiquetas pendientes</field>
        <field name="res_model">product.price.watch</field>
        <field name="view_mode">list</field>
        <field name="view_id" ref="product_price_watch_view_list_labels"/>
        <field name="context">{'search_default_filter_label_pending': 1}</field>
    </record>

    <record id="action_price_watch_markup" model="ir.actions.act_window">
        <field name="name">Margen erosionado</field>
        <field name="res_model">product.price.watch</field>
        <field name="view_mode">list</field>
        <field name="view_id" ref="product_price_watch_view_list_markup"/>
        <field name="context">{'search_default_filter_below': 1}</field>
    </record>
</odoo>
```

- [ ] **Paso 4: `views/product_category_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_category_form_target_markup" model="ir.ui.view">
        <field name="name">product.category.form.target.markup</field>
        <field name="model">product.category</field>
        <field name="inherit_id" ref="product.product_category_form_view"/>
        <field name="arch" type="xml">
            <xpath expr="//group[@name='first']" position="inside">
                <field name="target_markup_pct" readonly="not can_edit_commercial_conditions"/>
            </xpath>
        </field>
    </record>
</odoo>
```

> `can_edit_commercial_conditions` ya está en la vista por el punto 1
> (`product_category_form_internal_tax`). Si el orden de herencia hace que no esté
> disponible, agregar `<field name="can_edit_commercial_conditions" invisible="1"/>`.

- [ ] **Paso 5: `views/product_template_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_product_template_form_target_markup" model="ir.ui.view">
        <field name="name">product.template.form.target.markup</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="alpardata_purchase_replacement_cost.view_product_template_form_replacement_cost"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='internal_tax_pct']" position="after">
                <field name="target_markup_pct" readonly="not can_edit_commercial_conditions"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 6: `views/res_config_settings_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="res_config_settings_view_form_shelf" model="ir.ui.view">
        <field name="name">res.config.settings.form.shelf</field>
        <field name="model">res.config.settings</field>
        <field name="inherit_id" ref="alpardata_purchase_reference_cost.res_config_settings_view_form_reference_cost"/>
        <field name="arch" type="xml">
            <xpath expr="//block[@name='reference_cost_settings']" position="inside">
                <setting string="Góndola"
                         help="Lista con la que se imprimen las etiquetas de góndola y tolerancia antes de alertar margen bajo.">
                    <div class="content-group">
                        <div class="row">
                            <label for="shelf_pricelist_id" class="col-lg-5 o_light_label"/>
                            <field name="shelf_pricelist_id" class="col-lg-6"/>
                        </div>
                        <div class="row mt4">
                            <label for="markup_tolerance_pct" class="col-lg-5 o_light_label"/>
                            <field name="markup_tolerance_pct" class="col-lg-2"/>
                        </div>
                    </div>
                </setting>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 7: `views/product_label_layout_views.xml`** (aviso en el wizard)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_label_layout_form_shelf_warning" model="ir.ui.view">
        <field name="name">product.label.layout.form.shelf.warning</field>
        <field name="model">product.label.layout</field>
        <field name="inherit_id" ref="product.product_label_layout_form"/>
        <field name="arch" type="xml">
            <xpath expr="//form/*[1]" position="before">
                <div class="alert alert-warning" role="alert" invisible="not shelf_pricelist_warning">
                    <field name="shelf_pricelist_warning" nolabel="1"/>
                </div>
            </xpath>
        </field>
    </record>
</odoo>
```

> Verificar el id de la vista del wizard en `odoo-19.0/addons/product/wizard/product_label_layout_views.xml`.

- [ ] **Paso 8: `views/menus.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_price_watch_labels"
              name="Etiquetas pendientes"
              parent="stock.menu_stock_inventory_control"
              action="action_price_watch_labels"
              sequence="90"/>
    <menuitem id="menu_price_watch_markup"
              name="Margen erosionado"
              parent="alpardata_purchase_reference_cost.menu_reference_cost_root"
              action="action_price_watch_markup"
              sequence="40"/>
</odoo>
```

- [ ] **Paso 9: manifest `data`** completo:

```python
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/product_price_watch_views.xml',
        'views/product_category_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_label_layout_views.xml',
        'views/menus.xml',
    ],
```

- [ ] **Paso 10: instalar en base limpia** y correr todos los tests:

```bash
odoo-bin -c odoo.conf -d odoo19_labels_test -i alpardata_price_change_labels --test-enable --test-tags /alpardata_price_change_labels --stop-after-init --log-level=test
```
Esperado: 0 fallas; el `post_init_hook` no rompe.

- [ ] **Paso 11: prueba manual** (anotar en el PR): configurar lista de góndola, cambiar el
precio de un producto, "Actualizar" → aparece en Etiquetas pendientes; "Imprimir
etiquetas" → sale el PDF 3x8 y la fila desaparece.

- [ ] **Paso 12: commit**

```bash
git add alpardata_price_change_labels
git commit -m "feat(price_change_labels): seguridad, cron, vistas y menús"
```

---

### Tarea 5: Aplicar precio sugerido (productos con precio fijo)

**Files:** Modify `models/res_company.py`, `models/res_config_settings.py`,
`models/product_price_watch.py`, `views/product_price_watch_views.xml`,
`views/res_config_settings_views.xml`, `tests/__init__.py`; Create
`tests/test_suggested_price.py`.

- [ ] **Paso 1: test que falla** — `tests/test_suggested_price.py`

```python
from __future__ import annotations

from odoo.tests import tagged

from .common import PriceWatchCommon


@tagged('post_install', '-at_install')
class TestSuggestedPrice(PriceWatchCommon):

    def test_suggested_without_rounding(self):
        # reposición 1000, recargo 40 → 1400 sin IVA → 1694 con IVA incluido
        self.assertAlmostEqual(self._watch()._suggested_list_price(), 1694.0, places=2)

    def test_suggested_with_rounding_and_surcharge(self):
        self.company.write({'suggested_price_rounding': 10.0, 'suggested_price_surcharge': -1.0})
        self.seller.reference_cost = 1100.0  # 1540 sin IVA → 1863,40 → 1870 − 1
        self.assertAlmostEqual(self._watch()._suggested_list_price(), 1869.0, places=2)

    def test_apply_updates_list_price(self):
        self.company.write({'suggested_price_rounding': 10.0, 'suggested_price_surcharge': -1.0})
        self.seller.reference_cost = 1100.0
        self._watch().action_apply_suggested_price()
        self.assertEqual(self.template.list_price, 1869.0)
        self.assertAlmostEqual(self._watch().shelf_price, 1869.0, places=2)

    def test_apply_with_pricelist_rule_warns(self):
        self.company.shelf_pricelist_id = self.env['product.pricelist'].create({
            'name': 'Góndola fija',
            'item_ids': [(0, 0, {
                'applied_on': '3_global', 'compute_price': 'fixed', 'fixed_price': 2000.0,
            })],
        })
        self.seller.reference_cost = 1100.0
        result = self._watch().action_apply_suggested_price()
        self.assertEqual(result['tag'], 'display_notification')

    def test_no_cost_skipped(self):
        template = self.env['product.template'].create({
            'name': 'Sin costo', 'sale_ok': True, 'list_price': 50.0,
        })
        self.watch_model._refresh(template, self.company).action_apply_suggested_price()
        self.assertEqual(template.list_price, 50.0)
```

Agregar `from . import test_suggested_price` a `tests/__init__.py`.

- [ ] **Paso 2: correr** → falla.

- [ ] **Paso 3: `models/res_company.py`** — agregar a la clase:

```python
    suggested_price_rounding = fields.Float(
        string='Redondear precio sugerido a múltiplos de', default=0.0,
        help='0: sin redondeo. Ej.: 10 redondea hacia arriba a la decena.',
    )
    suggested_price_surcharge = fields.Float(
        string='Ajuste del precio sugerido', default=0.0,
        help='Se suma después del redondeo. Ej.: −1 para terminar en 9.',
    )
```

y a `models/res_config_settings.py`:

```python
    suggested_price_rounding = fields.Float(
        related='company_id.suggested_price_rounding', readonly=False,
    )
    suggested_price_surcharge = fields.Float(
        related='company_id.suggested_price_surcharge', readonly=False,
    )
```

- [ ] **Paso 4: `models/product_price_watch.py`** — sumar a los imports:

```python
import math

from odoo.tools import float_round
```

(`float_compare` y `_` ya están importados desde la tarea 2) y agregar a la clase:

```python
    def _suggested_list_price(self) -> float:
        """Precio de venta sugerido: reposición × (1 + recargo objetivo), con los
        impuestos incluidos en precio y el redondeo comercial de la empresa.
        0.0 si no hay costo de reposición."""
        self.ensure_one()
        if not self.replacement_cost:
            return 0.0
        template = self.product_tmpl_id
        company = self.company_id
        price = self.replacement_cost * (1 + template.target_markup_pct / 100)
        included = template.taxes_id.filtered(
            lambda t: t.company_id == company and t.amount_type == 'percent' and t.price_include
        )
        price *= 1 + sum(included.mapped('amount')) / 100
        if company.suggested_price_rounding > 0:
            steps = float_round(price / company.suggested_price_rounding, precision_digits=6)
            price = math.ceil(steps) * company.suggested_price_rounding
        return max(price + company.suggested_price_surcharge, 0.0)

    def action_apply_suggested_price(self):
        not_moved = self.browse()
        for rec in self:
            new_price = rec._suggested_list_price()
            if not new_price:
                continue
            before = rec.shelf_price
            rec.product_tmpl_id.list_price = new_price
            refreshed = self._refresh(rec.product_tmpl_id, rec.company_id)
            if (float_compare(refreshed.shelf_price, before, precision_digits=2) == 0
                    and float_compare(new_price, before, precision_digits=2) != 0):
                not_moved |= rec
        if not_moved:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Precio sugerido'),
                    'message': _(
                        '%s producto(s) no cambiaron de precio en góndola: su precio sale '
                        'de una regla de la lista de góndola, no del precio de venta.',
                        len(not_moved),
                    ),
                    'type': 'warning',
                    'sticky': True,
                },
            }
        return True
```

> `price_include` es el campo computado de `account.tax` en 19 (depende de
> `price_include_override` y de la configuración de la empresa). Verificarlo en
> `odoo-19.0/addons/account/models/account_tax.py`.

- [ ] **Paso 5: vistas** — en `views/product_price_watch_views.xml`, dentro del
`<header>` de `product_price_watch_view_list_markup`, antes del botón "Actualizar":

```xml
                    <button name="action_apply_suggested_price" type="object"
                            string="Aplicar precio sugerido" class="btn-primary"
                            groups="purchase.group_purchase_manager"
                            confirm="Se reemplaza el precio de venta de los productos seleccionados por el sugerido. ¿Continuar?"/>
```

En `views/res_config_settings_views.xml`, al final del `content-group` del setting
"Góndola":

```xml
                        <div class="row mt4">
                            <label for="suggested_price_rounding" class="col-lg-5 o_light_label"/>
                            <field name="suggested_price_rounding" class="col-lg-2"/>
                        </div>
                        <div class="row mt4">
                            <label for="suggested_price_surcharge" class="col-lg-5 o_light_label"/>
                            <field name="suggested_price_surcharge" class="col-lg-2"/>
                        </div>
```

- [ ] **Paso 6: correr** → `TestSuggestedPrice` pasa.

- [ ] **Paso 7: commit**

```bash
git add alpardata_price_change_labels
git commit -m "feat(price_change_labels): aplicar precio sugerido a productos con precio fijo"
```

---

### Tarea 6: README y PR

- [ ] **Paso 1: `README.md`**: qué resuelve, cómo configurar lista de góndola y recargo
objetivo, cuándo se actualiza (cron diario + botón), qué vacía la cola (sólo 3x8 regular
con la lista de góndola), y la sección **Redondeo comercial** del spec (terminar en 99:
redondeo 100 y recargo −1; múltiplos de 50: redondeo 50) usando las reglas de lista
estándar. Sumar "Aplicar precio sugerido": para qué productos sirve (precio fijo), la
fórmula, el redondeo, y que `list_price` es el mismo para todas las empresas.
- [ ] **Paso 2: commit, push y PR contra `19.0`.**

```bash
git add alpardata_price_change_labels/README.md
git commit -m "docs(price_change_labels): README"
git push -u origin feat/price-change-labels
```
