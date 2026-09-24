# Costo de Reposición sobre Adhoc + Migración de Broda — Plan de implementación

> **Para agentes:** implementar tarea por tarea, en orden. Cada paso usa checkbox (`- [ ]`).
> Si usás superpowers: REQUIRED SUB-SKILL `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`.

**Goal:** Crear `alpardata_replenishment_cost` (extensión de `product_replenishment_cost`
de Adhoc: vigencias, jerarquía de empresas, UoM, regla por proveedor, margen por
categoría, historial, cierre de vigencias) y `alpardata_reference_cost_migration`
(migración de un solo uso de Grupo Broda desde `alpardata_purchase_reference_cost`).

**Architecture:** La extensión sobreescribe un método del core
(`product.supplierinfo._get_filtered_supplier`) para la jerarquía de empresas, y uno de
Adhoc (`product.template._compute_supplier_data`) para vigencias, orden y UoM. Regla por
proveedor y margen por categoría son campos de Adhoc redefinidos como computados
editables. La migración es un módulo aparte cuyo `post_init_hook` ejecuta funciones
puras de paso (testeables), y deja un CSV de verificación.

**Tech Stack:** Odoo 19.0; `AlparLabs/product` rama `19.0` (Adhoc) — probado contra el
commit `9e7ea9026fe1ceb2aa764b47955c7e1c409720c3` (2026-09-22).

**Spec:** `docs/superpowers/specs/2026-09-24-adhoc-replenishment-cost-design.md` — leelo
antes de empezar.

---

## Convenciones

- **Rama:** `feat/adhoc-replenishment-cost` desde `19.0` de `AlparLabs/enhancement-suite`.
- **Addons path de desarrollo:** además de `enhancement-suite`, tiene que estar
  `AlparLabs/product` (rama `19.0`) clonado. Sin eso, los módulos no instalan.

  ```bash
  git clone -b 19.0 https://github.com/AlparLabs/product.git ../adhoc-product
  ```

  y agregar `../adhoc-product` al `addons_path` del `odoo.conf`.
- Strings, docstrings y commits en castellano. Commits:
  `feat(replenishment_cost): ...`, `feat(reference_cost_migration): ...`.
- **Odoo 19:** `<list>`, `invisible="expr"`, `<chatter/>`, `<search>` sin
  `<group string>`, `models.Constraint`, `res.groups` con `group_ids`.
- **Código de Adhoc que se extiende** (leerlo antes, en `../adhoc-product`):
  - `product_replenishment_cost/models/product_template.py` — `_compute_supplier_data`,
    `_compute_replenishment_cost`, campo `replenishment_cost_type`.
  - `product_replenishment_cost/models/product_supplierinfo.py` — `net_price`,
    `replenishment_cost_rule_id`, `last_date_price_updated`.
  - `product_replenishment_cost/models/product_replenishment_cost_rule.py` — `compute_rule`.
  - `product_planned_price/models/product_template.py` — `sale_margin`,
    `list_price_type`, `computed_list_price`.
- **Core que se extiende:** `odoo-19.0/addons/product/models/product_supplierinfo.py`
  (`_get_filtered_supplier`) y `product_product.py` (`_prepare_sellers`,
  `_get_filtered_sellers`, `_select_seller`). Fuente local:
  `C:\Users\Santiago\Desktop\Odoo\odoo-19.0`.
- **Tests:**

  ```bash
  odoo-bin -c odoo.conf -d odoo19_dev -i alpardata_replenishment_cost --test-enable --test-tags /alpardata_replenishment_cost --stop-after-init --log-level=test
  ```

  (para la migración, ver la tarea 7). Sin instancia: `python -m py_compile` + parseo XML
  con lxml; commit con `[tests no ejecutados]`.

## Mapa de archivos

`alpardata_replenishment_cost/`:
- `__init__.py` (con `pre_init_hook`), `__manifest__.py`, `README.md`
- `models/__init__.py`
- `models/company_hierarchy.py` — helper de ranking de empresas (función pura)
- `models/product_supplierinfo.py` — jerarquía, regla por proveedor, historial, vigencias
- `models/product_template.py` — proveedor vigente, margen por categoría, botón historial
- `models/res_partner.py` — regla por proveedor
- `models/product_category.py` — margen por categoría
- `models/product_supplierinfo_price_history.py` — modelo de historial
- `security/ir.model.access.csv`, `security/security.xml`
- `views/res_partner_views.xml`, `views/product_supplierinfo_views.xml`,
  `views/product_template_views.xml`, `views/product_category_views.xml`,
  `views/product_supplierinfo_price_history_views.xml`
- `tests/__init__.py`, `tests/common.py`, `tests/test_hierarchy.py`,
  `tests/test_supplier_data.py`, `tests/test_rule_by_partner.py`,
  `tests/test_margin_by_category.py`, `tests/test_history.py`

`alpardata_reference_cost_migration/`:
- `__init__.py` (con `post_init_hook`), `__manifest__.py`, `README.md` (runbook)
- `migration.py` — funciones de paso
- `tests/__init__.py`, `tests/test_migration.py`

---

### Tarea 1: Esqueleto y jerarquía de empresas en las fichas de proveedor

**Files:** Create el esqueleto de `alpardata_replenishment_cost`,
`models/company_hierarchy.py`, `models/product_supplierinfo.py` (parcial),
`tests/common.py`, `tests/test_hierarchy.py`.

- [ ] **Paso 1: `__init__.py`**

```python
from . import models


def pre_init_hook(env):
    """Antes de instalar: si Adhoc ya estaba en uso, marca como "propios" la regla
    de las fichas y el margen de los productos que ya tienen valor, para que los
    computados nuevos (regla por proveedor, margen por categoría) no los pisen."""
    cr = env.cr
    cr.execute("""
        ALTER TABLE product_supplierinfo ADD COLUMN IF NOT EXISTS use_own_rule boolean;
        UPDATE product_supplierinfo SET use_own_rule = (replenishment_cost_rule_id IS NOT NULL);
        ALTER TABLE product_template ADD COLUMN IF NOT EXISTS use_own_margin boolean;
        UPDATE product_template SET use_own_margin = (COALESCE(sale_margin, 0) != 0);
    """)
```

> Las columnas `replenishment_cost_rule_id` y `sale_margin` existen porque Adhoc se instala
> antes (dependencia). En Broda los dos quedan en `false`: Adhoc recién se instala.

- [ ] **Paso 2: `__manifest__.py`**

```python
{
    'name': 'AlparData - Costo de Reposición (extensión Adhoc)',
    'version': '19.0.1.0.0',
    'summary': 'Vigencias por fecha, jerarquía de empresas, regla por proveedor, margen por categoría e historial sobre el costo de reposición de Adhoc',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Inventory/Purchase',
    'license': 'AGPL-3',
    'depends': [
        'product_replenishment_cost',
        'product_replenishment_cost_stock',
        'product_replenishment_cost_sale_margin',
        'product_planned_price',
    ],
    'data': [],  # la tarea 6 agrega seguridad y vistas
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
```

> Licencia AGPL-3 porque depende de módulos AGPL-3 de Adhoc.

- [ ] **Paso 3: `models/__init__.py`**

```python
from . import product_supplierinfo
# from . import product_template
# from . import res_partner
# from . import product_category
# from . import product_supplierinfo_price_history
```

`tests/__init__.py`:

```python
from . import test_hierarchy
# from . import test_supplier_data
# from . import test_rule_by_partner
# from . import test_margin_by_category
# from . import test_history
```

- [ ] **Paso 4: `tests/common.py`**

```python
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
```

- [ ] **Paso 5: test que falla** — `tests/test_hierarchy.py`

```python
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
```

- [ ] **Paso 6: correr** → falla (`test_branch_sees_main_company` y la OC).

- [ ] **Paso 7: `models/company_hierarchy.py`**

```python
"""Ranking de empresas para elegir fichas de proveedor: la empresa activa (0), su
matriz (1), la matriz de la matriz (2)... y las fichas globales (sin empresa) al
final."""
from __future__ import annotations


def company_ranks(company) -> dict[int, int]:
    ranks: dict[int, int] = {}
    current = company
    while current and current.id not in ranks:
        ranks[current.id] = len(ranks)
        current = current.parent_id
    return ranks


def seller_rank(seller, ranks: dict[int, int]) -> int:
    """Rank de la ficha: el de su empresa, o global (después de todas)."""
    if not seller.company_id:
        return len(ranks)
    return ranks.get(seller.company_id.id, len(ranks) + 1)
```

- [ ] **Paso 8: `models/product_supplierinfo.py`** (parcial; las tareas 3 y 5 lo amplían)

```python
from __future__ import annotations

from odoo import models

from .company_hierarchy import company_ranks, seller_rank


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    def _get_filtered_supplier(self, company_id, product_id, params=False):
        """Core: sólo empresa exacta o global. Acá: también las matrices de la
        empresa, y para cada proveedor sólo el nivel de empresa más específico.

        `product_id` falso significa "cualquier variante" (lo usa el cálculo del
        costo a nivel plantilla)."""
        ranks = company_ranks(company_id)
        candidates = self.filtered(
            lambda s: (not s.company_id or s.company_id.id in ranks)
            and s.partner_id.sudo().active
            and (not s.product_id or not product_id or s.product_id == product_id)
        )
        best: dict[int, int] = {}
        for seller in candidates:
            rank = seller_rank(seller, ranks)
            best[seller.partner_id.id] = min(best.get(seller.partner_id.id, rank), rank)
        return candidates.filtered(
            lambda s: seller_rank(s, ranks) == best[s.partner_id.id]
        )
```

> No se llama a `super()`: el método del core es un único `filtered` y acá se reemplaza su
> condición de empresa. Si una versión futura de Odoo agrega condiciones al core,
> incorporarlas acá (revisar `odoo-19.0/addons/product/models/product_supplierinfo.py`).

- [ ] **Paso 9: correr** → `TestSupplierHierarchy` pasa. Si la OC de la sucursal no toma
100, revisar que `_prepare_sellers` del core llame a `_get_filtered_supplier` con
`self.env.company` (la OC se crea con `with_company(self.branch)`).

- [ ] **Paso 10: commit**

```bash
git add alpardata_replenishment_cost
git commit -m "feat(replenishment_cost): fichas de proveedor con jerarquía sucursal, matriz y global"
```

---

### Tarea 2: Proveedor vigente para el costo del producto (fechas, orden, UoM)

**Files:** Create `models/product_template.py` (parcial), `tests/test_supplier_data.py`.

- [ ] **Paso 1: test que falla** — `tests/test_supplier_data.py`

```python
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
```

> Si la creación de la UoM falla en 19, copiar la forma de crearla de
> `alpardata_purchase_reference_cost/tests/test_purchase_line_price.py` (rama `19.0`,
> antes de borrarse el módulo) o de los tests de `uom` del core.

- [ ] **Paso 2: correr** → fallan los de fechas, UoM y orden por empresa. Descomentar
`product_template` en `models/__init__.py` y `test_supplier_data` en `tests/__init__.py`.

- [ ] **Paso 3: `models/product_template.py`**

```python
from __future__ import annotations

from datetime import datetime

from odoo import api, fields, models

from .company_hierarchy import company_ranks, seller_rank


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.depends_context('company')
    @api.depends(
        'seller_ids.net_price', 'seller_ids.currency_id', 'seller_ids.company_id',
        'seller_ids.date_start', 'seller_ids.date_end', 'seller_ids.sequence',
        'seller_ids.product_uom_id', 'seller_ids.last_date_price_updated',
        'replenishment_cost_type', 'uom_id',
    )
    def _compute_supplier_data(self):
        """Reemplaza el de Adhoc: sólo fichas vigentes hoy, jerarquía de empresas,
        orden como el módulo anterior (empresa, secuencia, inicio más reciente, id)
        y precio convertido a la unidad del producto."""
        today = fields.Date.context_today(self)
        company = self.env.company
        ranks = company_ranks(company)
        empty_currency = self.env['res.currency']
        for rec in self:
            sellers = rec.seller_ids._get_filtered_supplier(company, False).filtered(
                lambda s: (not s.date_start or s.date_start <= today)
                and (not s.date_end or s.date_end >= today)
                and s.net_price > 0
            )
            if rec.replenishment_cost_type == 'last_supplier_price':
                sellers = sellers.sorted(
                    key=lambda s: s.last_date_price_updated or datetime.min, reverse=True,
                )
            else:
                sellers = sellers.sorted(key=lambda s: (
                    seller_rank(s, ranks),
                    s.sequence,
                    -(s.date_start.toordinal() if s.date_start else 0),
                    s.id,
                ))
            seller = sellers[:1]
            price = seller.net_price if seller else 0.0
            if seller and seller.product_uom_id and rec.uom_id and seller.product_uom_id != rec.uom_id:
                price = seller.product_uom_id._compute_price(price, rec.uom_id)
            rec.update({
                'supplier_price': price,
                'supplier_currency_id': seller.currency_id if seller else empty_currency,
            })
```

> No se llama a `super()` a propósito: el de Adhoc toma el primer proveedor sin fechas ni
> UoM. Este lo reemplaza entero. Si Adhoc cambia la firma o los campos que llena
> (`supplier_price`, `supplier_currency_id`), ajustar acá.
>
> `-(ordinal)` con 0 para "sin fecha" deja las fichas sin `date_start` después de las que
> tienen fecha, a igual empresa y secuencia.

- [ ] **Paso 4: correr** → `TestSupplierData` pasa. Correr también los tests de Adhoc
(`--test-tags /product_replenishment_cost`): alguno puede depender del orden viejo
(primer proveedor sin mirar fechas). Si falla uno de Adhoc por eso, anotarlo en el PR;
no modificar los tests de Adhoc.

- [ ] **Paso 5: commit**

```bash
git add alpardata_replenishment_cost
git commit -m "feat(replenishment_cost): costo del producto con fichas vigentes, jerarquía y unidad de medida"
```

---

### Tarea 3: Regla de costo por proveedor

**Files:** Create `models/res_partner.py`, `tests/test_rule_by_partner.py`; Modify
`models/product_supplierinfo.py`.

- [ ] **Paso 1: test que falla** — `tests/test_rule_by_partner.py`

```python
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
```

> `Form(seller)` usa la vista de formulario de la ficha: el campo tiene que estar en la
> vista (Adhoc lo pone en `product_replenishment_cost.product_supplierinfo_form_view`).
> Si el test de formulario falla porque falta el campo `use_own_rule` en la vista, se
> resuelve en la tarea 6; mover este test a después de la tarea 6 si hace falta.

- [ ] **Paso 2: correr** → falla. Descomentar `res_partner` en `models/__init__.py` y
`test_rule_by_partner` en `tests/__init__.py`.

- [ ] **Paso 3: `models/res_partner.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    replenishment_cost_rule_id = fields.Many2one(
        'product.replenishment_cost.rule',
        string='Regla de costo',
        help='Regla de bonificaciones y recargos que heredan las fichas de este '
             'proveedor, salvo las que tengan regla propia.',
    )
```

- [ ] **Paso 4: agregar a `models/product_supplierinfo.py`** (imports: sumar `api, fields`
a `from odoo import models`):

```python
    use_own_rule = fields.Boolean(
        string='Regla propia',
        help='Si está tildado, la ficha conserva su regla aunque cambie la del proveedor.',
    )
    replenishment_cost_rule_id = fields.Many2one(
        compute='_compute_replenishment_cost_rule_id',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('partner_id.commercial_partner_id.replenishment_cost_rule_id', 'use_own_rule')
    def _compute_replenishment_cost_rule_id(self) -> None:
        for rec in self:
            if not rec.use_own_rule:
                rec.replenishment_cost_rule_id = (
                    rec.partner_id.commercial_partner_id.replenishment_cost_rule_id
                )
            # Con regla propia no se asigna: el campo es editable y almacenado, y
            # conserva el valor cargado.

    @api.onchange('replenishment_cost_rule_id')
    def _onchange_replenishment_cost_rule_id_own(self) -> None:
        partner_rule = self.partner_id.commercial_partner_id.replenishment_cost_rule_id
        if self.replenishment_cost_rule_id != partner_rule:
            self.use_own_rule = True
```

> Si Odoo levanta "Compute method failed to assign" para las fichas con regla propia,
> reemplazar el comentario por `rec.replenishment_cost_rule_id = rec.replenishment_cost_rule_id`.

- [ ] **Paso 5: correr** → `TestRuleByPartner` pasa (salvo, quizá, el de formulario; ver
nota del paso 1).

- [ ] **Paso 6: commit**

```bash
git add alpardata_replenishment_cost
git commit -m "feat(replenishment_cost): regla de costo por proveedor heredada por sus fichas"
```

---

### Tarea 4: Margen por categoría

**Files:** Create `models/product_category.py`, `tests/test_margin_by_category.py`;
Modify `models/product_template.py`.

- [ ] **Paso 1: test que falla** — `tests/test_margin_by_category.py`

```python
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
```

> `computed_list_price` usa `replenishment_cost_main_company` (costo en la empresa
> principal del producto, ver `product_planned_price`). La ficha es global para que el
> test no dependa de qué empresa considera "principal".

- [ ] **Paso 2: correr** → falla. Descomentar `product_category` y
`test_margin_by_category`.

- [ ] **Paso 3: `models/product_category.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    sale_margin = fields.Float(
        string='Margen de venta (%)',
        digits='Discount',
        help='Margen del precio planificado que heredan los productos de esta '
             'categoría, salvo los que tengan margen propio.',
    )
```

- [ ] **Paso 4: agregar a `models/product_template.py`**

```python
    use_own_margin = fields.Boolean(
        string='Margen propio',
        help='Si está tildado, el producto conserva su margen aunque cambie el de la categoría.',
    )
    sale_margin = fields.Float(
        compute='_compute_sale_margin',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('categ_id.sale_margin', 'use_own_margin')
    def _compute_sale_margin(self) -> None:
        for rec in self:
            if not rec.use_own_margin:
                rec.sale_margin = rec.categ_id.sale_margin

    @api.onchange('sale_margin')
    def _onchange_sale_margin_own(self) -> None:
        if self.sale_margin != self.categ_id.sale_margin:
            self.use_own_margin = True
```

> Misma nota que la tarea 3 si Odoo exige asignar en todas las ramas.

- [ ] **Paso 5: correr** → pasa.

- [ ] **Paso 6: commit**

```bash
git add alpardata_replenishment_cost
git commit -m "feat(replenishment_cost): margen del precio planificado por categoría"
```

---

### Tarea 5: Historial de precios y cierre automático de vigencias

**Files:** Create `models/product_supplierinfo_price_history.py`,
`tests/test_history.py`; Modify `models/product_supplierinfo.py`,
`models/product_template.py`.

- [ ] **Paso 1: test que falla** — `tests/test_history.py`

```python
from __future__ import annotations

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ReplenishmentCommon


@tagged('post_install', '-at_install')
class TestPriceHistory(ReplenishmentCommon):

    def _history(self):
        return self.env['product.supplierinfo.price.history'].search([
            ('product_tmpl_id', '=', self.template.id),
        ], order='id asc')

    def test_create_logs_with_previous_price(self):
        self._seller(100.0, self.main_company)
        self._seller(120.0, self.main_company,
                     date_start=fields.Date.today())
        last = self._history()[-1]
        self.assertEqual(last.old_price, 100.0)
        self.assertEqual(last.new_price, 120.0)

    def test_price_change_logs_reason(self):
        seller = self._seller(100.0, self.main_company)
        seller.with_context(_change_reason='Lista marzo').price = 110.0
        last = self._history()[-1]
        self.assertEqual((last.old_price, last.new_price), (100.0, 110.0))
        self.assertEqual(last.change_reason, 'Lista marzo')
        self.assertEqual(last.changed_by, self.env.user)

    def test_rule_change_logs(self):
        rule = self.env['product.replenishment_cost.rule'].create({'name': 'R'})
        seller = self._seller(100.0, self.main_company)
        seller.write({'use_own_rule': True, 'replenishment_cost_rule_id': rule.id})
        self.assertEqual(self._history()[-1].new_rule_id, rule)

    def test_same_price_not_logged(self):
        seller = self._seller(100.0, self.main_company)
        count = len(self._history())
        seller.price = 100.0
        self.assertEqual(len(self._history()), count)

    def test_new_dated_seller_closes_previous(self):
        today = fields.Date.today()
        old = self._seller(100.0, self.main_company)
        self._seller(120.0, self.main_company, date_start=today)
        self.assertEqual(old.date_end, today - timedelta(days=1))

    def test_future_seller_not_closed(self):
        today = fields.Date.today()
        future = self._seller(150.0, self.main_company, date_start=today + timedelta(days=10))
        self._seller(120.0, self.main_company, date_start=today)
        self.assertFalse(future.date_end)

    def test_other_company_not_closed(self):
        today = fields.Date.today()
        other = self._seller(100.0, self.branch)
        self._seller(120.0, self.main_company, date_start=today)
        self.assertFalse(other.date_end)
```

- [ ] **Paso 2: correr** → falla. Descomentar `product_supplierinfo_price_history` y
`test_history`.

- [ ] **Paso 3: `models/product_supplierinfo_price_history.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class ProductSupplierinfoPriceHistory(models.Model):
    _name = 'product.supplierinfo.price.history'
    _description = 'Historial de precios de proveedor'
    _order = 'change_date desc, id desc'
    _rec_name = 'partner_id'

    supplierinfo_id = fields.Many2one(
        'product.supplierinfo', string='Ficha de proveedor', ondelete='set null', index=True,
    )
    product_tmpl_id = fields.Many2one(
        'product.template', string='Producto', ondelete='cascade', index=True,
    )
    partner_id = fields.Many2one('res.partner', string='Proveedor', index=True)
    company_id = fields.Many2one('res.company', string='Empresa', index=True)
    currency_id = fields.Many2one('res.currency', string='Moneda')
    old_price = fields.Float(string='Precio anterior', digits='Product Price')
    new_price = fields.Float(string='Precio nuevo', digits='Product Price')
    variation_pct = fields.Float(
        string='Variación (%)', compute='_compute_variation_pct', store=True, digits=(16, 2),
    )
    old_rule_id = fields.Many2one('product.replenishment_cost.rule', string='Regla anterior')
    new_rule_id = fields.Many2one('product.replenishment_cost.rule', string='Regla nueva')
    change_date = fields.Datetime(string='Fecha', default=fields.Datetime.now, index=True)
    changed_by = fields.Many2one('res.users', string='Usuario', default=lambda self: self.env.user)
    change_reason = fields.Char(string='Motivo')

    @api.depends('old_price', 'new_price')
    def _compute_variation_pct(self) -> None:
        for rec in self:
            rec.variation_pct = (
                (rec.new_price / rec.old_price - 1) * 100 if rec.old_price else 0.0
            )
```

- [ ] **Paso 4: agregar a `models/product_supplierinfo.py`** (imports: sumar
`from datetime import timedelta`):

```python
    price_history_count = fields.Integer(compute='_compute_price_history_count')

    def _compute_price_history_count(self) -> None:
        data = self.env['product.supplierinfo.price.history']._read_group(
            [('supplierinfo_id', 'in', self.ids)], ['supplierinfo_id'], ['__count'],
        )
        counts = {seller.id: count for seller, count in data}
        for rec in self:
            rec.price_history_count = counts.get(rec.id, 0)

    def _history_vals(self, old_price, new_price, old_rule, new_rule) -> dict:
        self.ensure_one()
        return {
            'supplierinfo_id': self.id,
            'product_tmpl_id': self.product_tmpl_id.id,
            'partner_id': self.partner_id.id,
            'company_id': (self.company_id or self.env.company).id,
            'currency_id': self.currency_id.id,
            'old_price': old_price,
            'new_price': new_price,
            'old_rule_id': old_rule.id if old_rule else False,
            'new_rule_id': new_rule.id if new_rule else False,
            'change_reason': self.env.context.get('_change_reason', 'Actualización manual'),
        }

    def _same_slot_domain(self) -> list:
        """Fichas del mismo proveedor, producto y empresa (excluyendo self)."""
        self.ensure_one()
        return [
            ('id', '!=', self.id),
            ('partner_id', '=', self.partner_id.id),
            ('product_tmpl_id', '=', self.product_tmpl_id.id),
            ('company_id', '=', self.company_id.id if self.company_id else False),
        ]

    def _previous_active(self):
        """Ficha vigente hoy del mismo proveedor, producto y empresa."""
        today = fields.Date.context_today(self)
        return self.sudo().search(self._same_slot_domain() + [
            '|', ('date_start', '=', False), ('date_start', '<=', today),
            '|', ('date_end', '=', False), ('date_end', '>=', today),
        ], order='sequence asc, id desc', limit=1)

    def _close_previous_records(self) -> None:
        """Al crear una ficha con fecha de inicio, cierra las anteriores del mismo
        proveedor, producto y empresa vigentes a esa fecha. No toca las que
        empiezan después."""
        self.ensure_one()
        if not self.date_start:
            return
        previous = self.sudo().search(self._same_slot_domain() + [
            '|', ('date_end', '=', False), ('date_end', '>=', self.date_start),
            '|', ('date_start', '=', False), ('date_start', '<', self.date_start),
        ])
        previous.write({'date_end': self.date_start - timedelta(days=1)})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        History = self.env['product.supplierinfo.price.history'].sudo()
        history_vals = []
        for rec in records:
            if not rec.product_tmpl_id:
                continue
            previous = rec._previous_active()
            history_vals.append(rec._history_vals(
                previous.price if previous else 0.0, rec.price,
                previous.replenishment_cost_rule_id if previous else False,
                rec.replenishment_cost_rule_id,
            ))
            rec._close_previous_records()
        History.create(history_vals)
        return records

    def write(self, vals):
        tracked = {'price', 'replenishment_cost_rule_id'} & set(vals)
        before = {}
        if tracked:
            before = {rec.id: (rec.price, rec.replenishment_cost_rule_id) for rec in self}
        res = super().write(vals)
        if tracked:
            history_vals = []
            for rec in self.filtered('product_tmpl_id'):
                old_price, old_rule = before[rec.id]
                if old_price != rec.price or old_rule != rec.replenishment_cost_rule_id:
                    history_vals.append(rec._history_vals(
                        old_price, rec.price, old_rule, rec.replenishment_cost_rule_id,
                    ))
            self.env['product.supplierinfo.price.history'].sudo().create(history_vals)
        return res

    def action_view_price_history(self) -> dict:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Historial de precios — {self.partner_id.name}',
            'res_model': 'product.supplierinfo.price.history',
            'view_mode': 'list',
            'domain': [('supplierinfo_id', '=', self.id)],
        }
```

> Nota: el cambio de regla por propagación desde el proveedor (tarea 3) no pasa por
> `write`, así que no queda en el historial. Es aceptado (el cambio queda en el
> proveedor). Documentarlo en el README.
>
> `_close_previous_records` excluye las que empiezan el mismo día o después
> (`date_start < self.date_start`): la ficha nueva no cierra otra cargada para el mismo
> día; ver `test_future_seller_not_closed`.

- [ ] **Paso 5: agregar a `models/product_template.py`**

```python
    def action_view_price_history(self) -> dict:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial de precios de proveedor',
            'res_model': 'product.supplierinfo.price.history',
            'view_mode': 'list',
            'domain': [('product_tmpl_id', '=', self.id)],
        }
```

- [ ] **Paso 6: ACL mínima** para que los tests carguen el modelo — crear
`security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_supplierinfo_price_history_user,product.supplierinfo.price.history.user,model_product_supplierinfo_price_history,purchase.group_purchase_user,1,0,0,0
access_supplierinfo_price_history_manager,product.supplierinfo.price.history.manager,model_product_supplierinfo_price_history,purchase.group_purchase_manager,1,0,0,1
```

y en el manifest `'data': ['security/ir.model.access.csv'],`.

- [ ] **Paso 7: correr** → `TestPriceHistory` pasa, y siguen pasando las tareas 1–4.

- [ ] **Paso 8: commit**

```bash
git add alpardata_replenishment_cost
git commit -m "feat(replenishment_cost): historial de precios de proveedor y cierre automático de vigencias"
```

---

### Tarea 6: Vistas, menú y reglas multi-empresa

**Files:** Create `security/security.xml` y las 5 vistas; Modify manifest.

- [ ] **Paso 1: `security/security.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="rule_supplierinfo_price_history_company" model="ir.rule">
        <field name="name">Historial de precios de proveedor: multi-empresa</field>
        <field name="model_id" ref="model_product_supplierinfo_price_history"/>
        <field name="global" eval="True"/>
        <field name="domain_force">['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]</field>
    </record>
</odoo>
```

- [ ] **Paso 2: `views/res_partner_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_partner_form_replenishment_rule" model="ir.ui.view">
        <field name="name">res.partner.form.replenishment.rule</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="purchase.view_partner_property_form"/>
        <field name="arch" type="xml">
            <xpath expr="//group[@name='purchase']" position="inside">
                <field name="replenishment_cost_rule_id" groups="purchase.group_purchase_user"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 3: `views/product_supplierinfo_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_supplierinfo_form_own_rule" model="ir.ui.view">
        <field name="name">product.supplierinfo.form.own.rule</field>
        <field name="model">product.supplierinfo</field>
        <field name="inherit_id" ref="product_replenishment_cost.product_supplierinfo_form_view"/>
        <field name="arch" type="xml">
            <field name="replenishment_cost_rule_id" position="after">
                <field name="use_own_rule"/>
            </field>
            <xpath expr="//sheet/group" position="before">
                <div class="oe_button_box" name="button_box">
                    <button name="action_view_price_history" type="object"
                            class="oe_stat_button" icon="fa-history"
                            groups="purchase.group_purchase_user">
                        <field name="price_history_count" widget="statinfo" string="Historial"/>
                    </button>
                </div>
            </xpath>
        </field>
    </record>

    <record id="product_supplierinfo_list_own_rule" model="ir.ui.view">
        <field name="name">product.supplierinfo.list.own.rule</field>
        <field name="model">product.supplierinfo</field>
        <field name="inherit_id" ref="product_replenishment_cost.product_supplierinfo_tree_view"/>
        <field name="arch" type="xml">
            <field name="replenishment_cost_rule_id" position="after">
                <field name="use_own_rule" optional="hide"/>
            </field>
        </field>
    </record>
</odoo>
```

> Verificar en `odoo-19.0/addons/product/views/product_supplierinfo_views.xml` que el form
> no tenga ya un `button_box` (en 19 no lo tiene; ver el módulo viejo, que agregaba uno
> igual).

- [ ] **Paso 4: `views/product_template_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_template_form_price_history" model="ir.ui.view">
        <field name="name">product.template.form.price.history</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product.product_template_form_view"/>
        <field name="arch" type="xml">
            <xpath expr="//div[@name='button_box']" position="inside">
                <button name="action_view_price_history" type="object"
                        class="oe_stat_button" icon="fa-history"
                        string="Historial de precios"
                        groups="purchase.group_purchase_user"/>
            </xpath>
        </field>
    </record>

    <record id="product_template_form_own_margin" model="ir.ui.view">
        <field name="name">product.template.form.own.margin</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product_planned_price.product_template_only_form_view"/>
        <field name="arch" type="xml">
            <field name="sale_margin" position="after">
                <field name="use_own_margin" string="propio" class="oe_inline"
                       invisible="list_price_type != 'by_margin'"/>
            </field>
        </field>
    </record>
</odoo>
```

> Revisar `product_planned_price/views/product_template_views.xml` (record
> `product_template_only_form_view`): `sale_margin` está dentro de un `div` con fórmula
> ("(costo × (1 + margen %) + recargo"). Si `position="after"` rompe la fórmula visual,
> mover `use_own_margin` a `position="before"` del label de la fórmula.

- [ ] **Paso 5: `views/product_category_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_category_form_sale_margin" model="ir.ui.view">
        <field name="name">product.category.form.sale.margin</field>
        <field name="model">product.category</field>
        <field name="inherit_id" ref="product.product_category_form_view"/>
        <field name="arch" type="xml">
            <xpath expr="//group[@name='first']" position="inside">
                <field name="sale_margin"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 6: `views/product_supplierinfo_price_history_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="supplierinfo_price_history_view_list" model="ir.ui.view">
        <field name="name">product.supplierinfo.price.history.list</field>
        <field name="model">product.supplierinfo.price.history</field>
        <field name="arch" type="xml">
            <list create="0" edit="0" delete="0">
                <field name="change_date"/>
                <field name="product_tmpl_id"/>
                <field name="partner_id"/>
                <field name="company_id" groups="base.group_multi_company" optional="show"/>
                <field name="old_price"/>
                <field name="new_price"/>
                <field name="variation_pct"
                       decoration-danger="variation_pct &gt; 0"
                       decoration-success="variation_pct &lt; 0"/>
                <field name="old_rule_id" optional="hide"/>
                <field name="new_rule_id" optional="hide"/>
                <field name="changed_by"/>
                <field name="change_reason"/>
            </list>
        </field>
    </record>

    <record id="supplierinfo_price_history_view_search" model="ir.ui.view">
        <field name="name">product.supplierinfo.price.history.search</field>
        <field name="model">product.supplierinfo.price.history</field>
        <field name="arch" type="xml">
            <search>
                <field name="product_tmpl_id"/>
                <field name="partner_id"/>
                <field name="change_reason"/>
                <group>
                    <filter name="group_partner" string="Proveedor" context="{'group_by': 'partner_id'}"/>
                    <filter name="group_product" string="Producto" context="{'group_by': 'product_tmpl_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_supplierinfo_price_history" model="ir.actions.act_window">
        <field name="name">Historial de precios de proveedor</field>
        <field name="res_model">product.supplierinfo.price.history</field>
        <field name="view_mode">list</field>
    </record>

    <menuitem id="menu_supplierinfo_price_history"
              name="Historial de precios de proveedor"
              parent="purchase.menu_purchase_products"
              action="action_supplierinfo_price_history"
              groups="purchase.group_purchase_user"
              sequence="40"/>
</odoo>
```

- [ ] **Paso 7: manifest `data`**:

```python
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/res_partner_views.xml',
        'views/product_supplierinfo_views.xml',
        'views/product_template_views.xml',
        'views/product_category_views.xml',
        'views/product_supplierinfo_price_history_views.xml',
    ],
```

- [ ] **Paso 8: instalar en base limpia y correr todos los tests** (incluido
`test_editing_rule_in_form_marks_own`) → 0 fallas.

- [ ] **Paso 9: commit**

```bash
git add alpardata_replenishment_cost
git commit -m "feat(replenishment_cost): vistas, historial en menú y reglas multi-empresa"
```

---

### Tarea 7: Módulo de migración

**Files:** Create `alpardata_reference_cost_migration/` completo.

> Los tests de esta tarea necesitan una base con **`alpardata_purchase_reference_cost` y
> `alpardata_replenishment_cost` instalados a la vez**. El módulo viejo se borra del repo
> recién después de migrar producción; mientras tanto sigue en `19.0`.

- [ ] **Paso 1: `__manifest__.py`**

```python
{
    'name': 'AlparData - Migración Costo de Referencia → Adhoc',
    'version': '19.0.1.0.0',
    'summary': 'Migración de un solo uso: listas e historial de alpardata_purchase_reference_cost al costo de reposición de Adhoc',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Hidden',
    'license': 'AGPL-3',
    'depends': ['alpardata_replenishment_cost', 'alpardata_purchase_reference_cost'],
    'data': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
```

- [ ] **Paso 2: `__init__.py`**

```python
from . import migration


def post_init_hook(env):
    migration.run(env)
```

- [ ] **Paso 3: test que falla** — `tests/test_migration.py` (y `tests/__init__.py` con
`from . import test_migration`)

```python
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
```

- [ ] **Paso 4: correr** → falla (no existe `migration`). Para correr los tests del módulo
de migración:

```bash
odoo-bin -c odoo.conf -d odoo19_mig -i alpardata_purchase_reference_cost,alpardata_replenishment_cost --stop-after-init
odoo-bin -c odoo.conf -d odoo19_mig -i alpardata_reference_cost_migration --test-enable --test-tags /alpardata_reference_cost_migration --stop-after-init --log-level=test
```

- [ ] **Paso 5: `migration.py`**

```python
"""Migración de alpardata_purchase_reference_cost al costo de reposición de Adhoc.

Cada paso es una función independiente (testeable). `run` los ejecuta en orden.
Ver el runbook en README.md.
"""
from __future__ import annotations

import base64
import csv
import io
import logging

from odoo import fields
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

OLD_BASES = ('reference_cost', 'replacement_cost')


def check_pricelist_bases(env) -> None:
    """Aborta si hay reglas de lista basadas en el costo de referencia/reposición:
    en Adhoc no existe esa base y no se decide en silencio a qué pasarlas."""
    items = env['product.pricelist.item'].sudo().with_context(active_test=False).search([
        ('base', 'in', OLD_BASES),
    ])
    if items:
        detail = ', '.join(f'{i.pricelist_id.display_name} (id {i.id})' for i in items[:20])
        raise UserError(
            f'Hay {len(items)} reglas de listas de precios con base en el costo de '
            f'referencia o de reposición: {detail}. Cambiales la base antes de migrar.'
        )


def _companies_to_check(env):
    """Empresas donde se compara el costo: las que tienen fichas y sus sucursales;
    si hay fichas globales, todas."""
    env.cr.execute(
        'SELECT DISTINCT company_id FROM product_supplierinfo WHERE reference_cost > 0'
    )
    company_ids = [row[0] for row in env.cr.fetchall()]
    Company = env['res.company'].sudo()
    if None in company_ids:
        return Company.search([])
    return Company.search([('id', 'child_of', company_ids)])


def _templates_with_lists(env):
    env.cr.execute("""
        SELECT DISTINCT product_tmpl_id FROM product_supplierinfo
        WHERE reference_cost > 0 AND product_tmpl_id IS NOT NULL
    """)
    return env['product.template'].sudo().browse([row[0] for row in env.cr.fetchall()])


def snapshot_costs(env) -> dict[tuple[int, int], float]:
    """{(company_id, product_tmpl_id): reference_cost} con el módulo viejo."""
    templates = _templates_with_lists(env)
    snapshot = {}
    for company in _companies_to_check(env):
        costs = templates.with_company(company).mapped('reference_cost')
        for template, cost in zip(templates, costs):
            snapshot[(company.id, template.id)] = cost
    return snapshot


def copy_prices(env) -> int:
    """price = reference_cost, por SQL (sin historial). La fecha de último precio de
    Adhoc toma la fecha de modificación de la ficha."""
    env.cr.execute("""
        UPDATE product_supplierinfo
           SET price = reference_cost,
               last_date_price_updated = write_date
         WHERE reference_cost > 0
    """)
    count = env.cr.rowcount
    env['product.supplierinfo'].invalidate_model(['price', 'last_date_price_updated'])
    _logger.info('Migración: %s fichas con price = reference_cost', count)
    return count


def copy_history(env) -> int:
    """Copia product_supplierinfo_cost_history → product_supplierinfo_price_history."""
    env.cr.execute("""
        INSERT INTO product_supplierinfo_price_history (
            supplierinfo_id, product_tmpl_id, partner_id, company_id, currency_id,
            old_price, new_price, variation_pct, change_date, changed_by, change_reason,
            create_uid, create_date, write_uid, write_date
        )
        SELECT h.supplierinfo_id, h.product_tmpl_id, h.partner_id, h.company_id,
               c.currency_id,
               h.old_reference_cost, h.new_reference_cost,
               CASE WHEN COALESCE(h.old_reference_cost, 0) = 0 THEN 0
                    ELSE (h.new_reference_cost / h.old_reference_cost - 1) * 100 END,
               h.change_date, h.changed_by, h.change_reason,
               h.create_uid, h.create_date, h.write_uid, h.write_date
          FROM product_supplierinfo_cost_history h
          LEFT JOIN res_company c ON c.id = h.company_id
    """)
    count = env.cr.rowcount
    _logger.info('Migración: %s registros de historial copiados', count)
    return count


def set_cost_types(env) -> int:
    """Productos con alguna ficha con precio → tipo "precio del proveedor principal"."""
    env.cr.execute("""
        UPDATE product_template t
           SET replenishment_cost_type = 'supplier_price'
         WHERE EXISTS (
             SELECT 1 FROM product_supplierinfo s
              WHERE s.product_tmpl_id = t.id AND s.price > 0
         )
    """)
    count = env.cr.rowcount
    env['product.template'].invalidate_model(['replenishment_cost_type'])
    _logger.info('Migración: %s productos pasan a supplier_price', count)
    return count


def verify(env, snapshot) -> list[dict]:
    """Compara el costo de reposición nuevo contra la foto previa."""
    precision = env['decimal.precision'].precision_get('Product Price')
    Template = env['product.template'].sudo()
    Company = env['res.company'].sudo()
    by_company: dict[int, list[int]] = {}
    for company_id, template_id in snapshot:
        by_company.setdefault(company_id, []).append(template_id)
    rows = []
    for company_id, template_ids in by_company.items():
        templates = Template.browse(template_ids).with_company(Company.browse(company_id))
        templates.invalidate_recordset()
        for template in templates:
            old = snapshot[(company_id, template.id)]
            new = template.replenishment_cost
            if float_compare(old, new, precision_digits=precision) != 0:
                rows.append({
                    'company_id': company_id,
                    'product_tmpl_id': template.id,
                    'product': template.display_name,
                    'old_cost': old,
                    'new_cost': new,
                    'difference': new - old,
                })
    _logger.info('Migración: %s diferencias de costo', len(rows))
    return rows


def write_report(env, rows):
    """Adjunta el CSV de diferencias a la empresa principal (id más bajo)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[
        'company_id', 'product_tmpl_id', 'product', 'old_cost', 'new_cost', 'difference',
    ])
    writer.writeheader()
    writer.writerows(rows)
    main_company = env['res.company'].sudo().search([], order='id asc', limit=1)
    return env['ir.attachment'].sudo().create({
        'name': f'migracion_costo_referencia_{fields.Date.today()}.csv',
        'datas': base64.b64encode(buffer.getvalue().encode('utf-8')),
        'res_model': 'res.company',
        'res_id': main_company.id,
        'mimetype': 'text/csv',
    })


def run(env) -> None:
    check_pricelist_bases(env)
    snapshot = snapshot_costs(env)
    copy_prices(env)
    copy_history(env)
    set_cost_types(env)
    rows = verify(env, snapshot)
    attachment = write_report(env, rows)
    _logger.warning(
        'Migración costo de referencia → Adhoc terminada: %s diferencias. '
        'CSV adjunto id %s en la empresa principal.', len(rows), attachment.id,
    )
```

> Verificar en el módulo viejo (`alpardata_purchase_reference_cost/models/product_supplierinfo_cost_history.py`)
> que las columnas `old_reference_cost`, `new_reference_cost`, `change_date`,
> `changed_by`, `change_reason`, `supplierinfo_id`, `product_tmpl_id`, `partner_id`,
> `company_id` existan con esos nombres (existen en la versión 19.0.2.x).
>
> `variation_pct` se inserta calculado porque es un computado almacenado y el `INSERT`
> por SQL no dispara el compute.

- [ ] **Paso 6: correr** → `TestMigration` pasa.

- [ ] **Paso 7: `README.md` (runbook)** — copiar el procedimiento del spec (sección
"Procedimiento") y agregar:
  - **Instalar desde la terminal de Odoo.sh**, no desde la interfaz (la migración de ~7.800
    fichas y ~12.000 registros de historial puede superar el tiempo límite de una petición
    web):

    ```bash
    odoo-bin -i alpardata_reference_cost_migration --stop-after-init
    ```
  - Descargar el CSV de **Ajustes → Técnico → Adjuntos** (nombre
    `migracion_costo_referencia_<fecha>.csv`) y confirmar 0 filas antes de desinstalar el
    módulo viejo.
  - Desinstalar después `alpardata_purchase_replacement_cost` (sólo en test) y
    `alpardata_purchase_reference_cost` (arrastra al de migración).

- [ ] **Paso 8: commit**

```bash
git add alpardata_reference_cost_migration
git commit -m "feat(reference_cost_migration): migración de listas e historial al costo de reposición de Adhoc"
```

---

### Tarea 8: README de la extensión y PR

- [ ] **Paso 1: `alpardata_replenishment_cost/README.md`**: qué agrega sobre Adhoc
(vigencias, jerarquía, UoM, regla por proveedor, margen por categoría, historial, cierre de
vigencias); cómo se elige la ficha (empresa más específica, secuencia, inicio más
reciente); que la regla y el margen se heredan salvo "propio"; que el cambio de regla
propagado desde el proveedor no queda en el historial; que activar precios "por margen" y
el cron de Adhoc es configuración comercial; que no se instala junto con
`alpardata_purchase_reference_cost` salvo durante la migración.

- [ ] **Paso 2: commit, push y PR contra `19.0`** con el resultado de los tests y la
aclaración de que el submódulo `AlparLabs/product` debe estar en el build.

```bash
git add alpardata_replenishment_cost/README.md
git commit -m "docs(replenishment_cost): README"
git push -u origin feat/adhoc-replenishment-cost
```

- [ ] **Paso 3: ensayo en `grupobroda-test`** siguiendo el runbook (restaurar desde
producción, instalar por terminal, revisar CSV, desinstalar módulos viejos, pruebas
manuales). Anotar el resultado en el PR antes de mergear.
