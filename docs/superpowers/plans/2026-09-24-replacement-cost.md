# Costo de Reposición Desglosado — Plan de implementación

> **OBSOLETO (2026-09-24):** reemplazado por `specs/2026-09-24-adhoc-replenishment-cost-design.md`
> (costo de reposición sobre `product_replenishment_cost` de Adhoc). Se conserva como referencia.

> **Para agentes:** implementar tarea por tarea, en orden. Cada paso usa checkbox (`- [ ]`).
> Si usás superpowers: REQUIRED SUB-SKILL `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`.

**Goal:** Crear `alpardata_purchase_replacement_cost`: costo de reposición por producto
(lista − bonificaciones en cascada − pronto pago + flete + percepción + impuestos
internos), usable como base de listas de precios, con bonificaciones aplicadas como
descuento en las órdenes de compra.

**Architecture:** Módulo nuevo que depende de `alpardata_purchase_reference_cost`. La
fórmula vive en funciones puras (`tools/`), los modelos sólo resuelven qué valores
aplican. Dos refactors mínimos en el módulo base exponen hooks
(`_convert_commercial_cost`, `_get_divergence_base_cost`) sin cambiar su comportamiento.

**Tech Stack:** Odoo 19.0 (ORM, vistas XML), Python 3.12.

**Spec:** `docs/superpowers/specs/2026-09-24-replacement-cost-design.md` — leelo antes de
empezar.

---

## Convenciones (leer antes de la tarea 1)

- **Rama:** `feat/replacement-cost` creada desde `19.0`.
- **Idioma:** strings, docstrings y commits en castellano (como el resto del repo).
- **Commits:** `feat(purchase_replacement_cost): ...`, `refactor(purchase_reference_cost): ...`,
  `test(...)`. Cerrar cada mensaje con:
  `Co-Authored-By: <tu agente> <...>` si tu herramienta lo agrega; no inventar coautores.
- **Odoo 19** (errores frecuentes, NO cometerlos):
  - Vistas: `<list>` (no `<tree>`), `invisible="expr"`/`readonly="expr"` (no `attrs`),
    `<chatter/>`, en `<search>` los `<group>` **no** llevan `string` ni `expand`.
  - `res.groups` usa `group_ids`/`privilege_id` (no `groups_id`/`category_id`).
  - Línea de OC: `technical_price_unit` marca precio manual; fijar precio sólo con
    `line._reset_price_unit(price)`.
  - `product.supplierinfo.product_uom_id` (no `product_uom`).
- **Fuente de Odoo para consultar:** `C:\Users\Santiago\Desktop\Odoo\odoo-19.0` (community)
  y `enterprise-19.0`. Verificar ahí cualquier firma antes de sobreescribir.
- **Correr tests** (reemplazar `odoo19_dev` y `-c` por tu entorno):

  ```bash
  odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_purchase_reference_cost,alpardata_purchase_replacement_cost --test-enable --test-tags /alpardata_purchase_reference_cost,/alpardata_purchase_replacement_cost --stop-after-init --log-level=test
  ```

  Si no tenés instancia Odoo, como mínimo: `python -m py_compile <archivo>` para cada
  `.py` y `python -c "import lxml.etree as e; e.parse('<archivo>.xml')"` para cada XML, y
  marcá en el commit `[tests no ejecutados]`.

## Mapa de archivos

Módulo base (`alpardata_purchase_reference_cost/`), modificar:
- `__manifest__.py` — versión `19.0.2.2.0`.
- `models/product_pricelist.py` — extraer `_convert_commercial_cost`.
- `models/product_template.py` — extraer `_get_divergence_base_cost`.

Módulo nuevo (`alpardata_purchase_replacement_cost/`), crear:
- `__init__.py`, `__manifest__.py`, `README.md`
- `tools/__init__.py`, `tools/discount_cascade.py` (parseo cascada),
  `tools/cost_formula.py` (fórmula)
- `models/__init__.py`
- `models/commercial_conditions_access.py` — mixin de permisos de edición
- `models/res_partner.py` — condiciones del proveedor
- `models/product_category.py` — `internal_tax_pct`
- `models/product_template.py` — `internal_tax_pct`, `replacement_cost`, `net_purchase_cost`, divergencia
- `models/product_product.py` — `_get_replacement_cost_for`
- `models/product_supplierinfo.py` — condiciones propias/efectivas, reposición, desglose
- `models/product_pricelist.py` — base `replacement_cost`
- `models/purchase_order_line.py`, `models/purchase_order.py` — descuento en cascada
- `views/res_partner_views.xml`, `views/product_supplierinfo_views.xml`,
  `views/product_template_views.xml`, `views/product_category_views.xml`,
  `views/purchase_order_views.xml`
- `tests/__init__.py`, `tests/common.py`, `tests/test_discount_cascade.py`,
  `tests/test_conditions.py`, `tests/test_replacement_cost.py`, `tests/test_pricelist.py`,
  `tests/test_purchase_order.py`, `tests/test_divergence.py`, `tests/test_access.py`

---

### Tarea 1: Refactor del módulo base (hooks sin cambio de comportamiento)

**Files:**
- Modify: `alpardata_purchase_reference_cost/models/product_pricelist.py`
- Modify: `alpardata_purchase_reference_cost/models/product_template.py`
- Modify: `alpardata_purchase_reference_cost/__manifest__.py`

- [ ] **Paso 1: correr los tests del base antes de tocar nada** y anotar que pasan.

```bash
odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_purchase_reference_cost --test-enable --test-tags /alpardata_purchase_reference_cost --stop-after-init --log-level=test
```
Esperado: `0 failed, 0 error(s)`.

- [ ] **Paso 2: extraer `_convert_commercial_cost` en `product_pricelist.py`.**
Reemplazar el cuerpo de `_compute_base_price` desde `# reference_cost is stored in the
company currency...` hasta `return ref_cost` por una llamada al helper, y agregar el helper:

```python
        return self._convert_commercial_cost(product, ref_cost, uom, date, currency)

    def _convert_commercial_cost(self, product, cost, uom, date, currency) -> float:
        """Convierte un costo comercial expresado en la UoM del producto y la
        moneda de la empresa a la UoM `uom` y la moneda `currency` de la regla.

        Lo usan todas las bases comerciales (referencia, reposición) para que la
        conversión sea idéntica.
        """
        if uom and product.uom_id and uom != product.uom_id:
            cost = product.uom_id._compute_price(cost, uom)
        src_currency = self.env.company.currency_id
        if src_currency != currency:
            cost = src_currency._convert(
                cost, currency, self.env.company, date, round=False
            )
        return cost
```

El bloque del fallback (`if not ref_cost: ... ref_cost = product.standard_price`) queda
igual, antes del `return`.

- [ ] **Paso 3: extraer `_get_divergence_base_cost` en `product_template.py`.**
En `_compute_cost_divergence`, reemplazar el uso directo de `rec.reference_cost` por una
variable `base_cost`:

```python
        for rec in self:
            base_cost = rec._get_divergence_base_cost()
            if not base_cost:
                rec.cost_divergence_pct = 0.0
                rec.cost_divergence_alert = 'ok'
                continue
            divergence = abs(
                (rec.standard_price - base_cost) / base_cost * 100
            )
```
(el resto del loop no cambia). Agregar el método debajo de `_compute_cost_divergence`:

```python
    def _get_divergence_base_cost(self) -> float:
        """Costo contra el que se compara el AVCO en el semáforo de divergencia.

        Hook: módulos que desglosan el costo (p. ej. reposición) lo sobreescriben
        para comparar contra el neto bonificado.
        """
        self.ensure_one()
        return self.reference_cost
```

- [ ] **Paso 4: subir versión** en `__manifest__.py`: `'version': '19.0.2.2.0',`.

- [ ] **Paso 5: correr los tests del base.** Esperado: mismos resultados que el paso 1,
**sin modificar ningún test**.

- [ ] **Paso 6: commit**

```bash
git add alpardata_purchase_reference_cost
git commit -m "refactor(purchase_reference_cost): exponer hooks de conversión y de costo de divergencia"
```

---

### Tarea 2: Esqueleto del módulo nuevo

**Files:** Create `alpardata_purchase_replacement_cost/__init__.py`,
`__manifest__.py`, `models/__init__.py`, `tools/__init__.py`, `tests/__init__.py`.

- [ ] **Paso 1: `__init__.py`**

```python
from . import models
```

- [ ] **Paso 2: `__manifest__.py`**

```python
{
    'name': 'AlparData - Costo de Reposición',
    'version': '19.0.1.0.0',
    'summary': 'Costo de reposición: lista con bonificaciones en cascada, pronto pago, flete, percepciones e impuestos internos',
    'description': """
        Extiende el Costo de Referencia con un Costo de Reposición desglosado:

            neto       = lista × (1 − b1) × (1 − b2) × …
            reposición = neto × (1 − pronto pago + flete + percepción + internos)

        - Condiciones comerciales por proveedor (por empresa), con excepción por
          ficha de proveedor del producto.
        - Impuestos internos por categoría y producto.
        - Base "Costo de Reposición" en listas de precios.
        - Bonificaciones en cascada como descuento en órdenes de compra.
        - Semáforo de divergencia contra el neto bonificado.
    """,
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Inventory/Purchase',
    'depends': ['alpardata_purchase_reference_cost'],
    'data': [],  # la tarea 11 agrega las vistas
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

- [ ] **Paso 3: `models/__init__.py`** — todas las líneas comentadas; cada tarea
descomenta la suya al crear el archivo:

```python
# from . import commercial_conditions_access
# from . import res_partner
# from . import product_category
# from . import product_template
# from . import product_product
# from . import product_supplierinfo
# from . import product_pricelist
# from . import purchase_order_line
# from . import purchase_order
```

- [ ] **Paso 4: `tools/__init__.py`**

```python
from .discount_cascade import cascade_equivalent_pct, parse_discount_cascade
from .cost_formula import compute_replacement_cost
```

- [ ] **Paso 5: `tests/__init__.py`** — igual, todo comentado menos el test de la tarea 3:

```python
from . import test_discount_cascade
# from . import test_conditions
# from . import test_replacement_cost
# from . import test_pricelist
# from . import test_purchase_order
# from . import test_divergence
# from . import test_access
```

- [ ] **Paso 6:** no commitear todavía: el esqueleto se commitea junto con la tarea 3.
(El manifest arranca con `'data': []`; la tarea 11 agrega las vistas.)

---

### Tarea 3: Parseo de la cascada y fórmula (funciones puras)

**Files:**
- Create: `alpardata_purchase_replacement_cost/tools/discount_cascade.py`
- Create: `alpardata_purchase_replacement_cost/tools/cost_formula.py`
- Test: `alpardata_purchase_replacement_cost/tests/test_discount_cascade.py`

- [ ] **Paso 1: test que falla** — `tests/test_discount_cascade.py`

```python
from __future__ import annotations

from odoo.tests import tagged
from odoo.tests.common import BaseCase

from odoo.addons.alpardata_purchase_replacement_cost.tools import (
    cascade_equivalent_pct,
    compute_replacement_cost,
    parse_discount_cascade,
)


@tagged('post_install', '-at_install')
class TestDiscountCascade(BaseCase):

    def test_parse_simple(self):
        self.assertEqual(parse_discount_cascade('10+5+3'), [10.0, 5.0, 3.0])

    def test_parse_spaces_and_comma_decimal(self):
        self.assertEqual(parse_discount_cascade(' 10 + 2,5 '), [10.0, 2.5])
        self.assertEqual(parse_discount_cascade('7.5'), [7.5])

    def test_parse_empty(self):
        self.assertEqual(parse_discount_cascade(False), [])
        self.assertEqual(parse_discount_cascade(''), [])
        self.assertEqual(parse_discount_cascade('   '), [])

    def test_parse_invalid(self):
        for text in ('abc', '10++5', '10+', '+10', '100', '0', '-5', '10+105', '10;5'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_discount_cascade(text)

    def test_equivalent(self):
        self.assertAlmostEqual(cascade_equivalent_pct([10, 5, 3]), 17.065, places=6)
        self.assertEqual(cascade_equivalent_pct([]), 0.0)

    def test_formula_canonical_example(self):
        net, replacement = compute_replacement_cost(
            list_price=1000.0,
            discount_equivalent_pct=17.065,
            early_payment_pct=2.0,
            freight_pct=3.5,
            perception_pct=1.5,
            internal_tax_pct=0.0,
        )
        self.assertAlmostEqual(net, 829.35, places=6)
        self.assertAlmostEqual(replacement, 854.2305, places=6)

    def test_formula_zero_list(self):
        self.assertEqual(compute_replacement_cost(0.0, 10.0, 0, 0, 0, 0), (0.0, 0.0))
```

- [ ] **Paso 2: correr y ver que falla** (ImportError: `tools` vacío). Comando de la sección
Convenciones, con sólo `/alpardata_purchase_replacement_cost`.

- [ ] **Paso 3: implementar `tools/discount_cascade.py`**

```python
"""Bonificaciones en cascada ("10+5+3").

Funciones puras, sin dependencias de Odoo, para poder reutilizarlas desde otros
módulos (p. ej. el importador de listas de proveedores).
"""
from __future__ import annotations

import re

_NUMBER = r'\d+(?:[.,]\d+)?'
_CASCADE_RE = re.compile(rf'^{_NUMBER}(?:\+{_NUMBER})*$')


def parse_discount_cascade(text: str | bool | None) -> list[float]:
    """Parsea una cascada de bonificaciones.

    Acepta espacios y coma o punto decimal. Vacío → []. Cada valor debe ser
    mayor que 0 y menor que 100. Formato inválido → ValueError.
    """
    if not text or not str(text).strip():
        return []
    compact = re.sub(r'\s+', '', str(text))
    if not _CASCADE_RE.match(compact):
        raise ValueError(
            f'Bonificaciones "{text}" con formato inválido. '
            'Usá números separados por "+", por ejemplo 10+5+3 o 10+2,5.'
        )
    values = [float(part.replace(',', '.')) for part in compact.split('+')]
    for value in values:
        if not 0 < value < 100:
            raise ValueError(
                f'Bonificación {value:g} fuera de rango en "{text}": '
                'cada valor debe ser mayor que 0 y menor que 100.'
            )
    return values


def cascade_equivalent_pct(values: list[float]) -> float:
    """Porcentaje único equivalente a aplicar las bonificaciones en cascada."""
    factor = 1.0
    for value in values:
        factor *= 1 - value / 100
    return (1 - factor) * 100
```

- [ ] **Paso 4: implementar `tools/cost_formula.py`**

```python
"""Fórmula del costo de reposición.

    neto       = lista × (1 − equivalente_bonificación)
    reposición = neto × (1 − pronto_pago + flete + percepción + internos)

Todos los adicionales se calculan sobre el neto bonificado y no se componen entre
sí (ver spec 2026-09-24-replacement-cost-design.md).
"""
from __future__ import annotations


def compute_replacement_cost(
    list_price: float,
    discount_equivalent_pct: float,
    early_payment_pct: float,
    freight_pct: float,
    perception_pct: float,
    internal_tax_pct: float,
) -> tuple[float, float]:
    """Devuelve (neto bonificado, costo de reposición)."""
    if not list_price:
        return 0.0, 0.0
    net = list_price * (1 - discount_equivalent_pct / 100)
    factor = 1 + (
        -early_payment_pct + freight_pct + perception_pct + internal_tax_pct
    ) / 100
    return net, net * factor
```

- [ ] **Paso 5: correr tests** → `TestDiscountCascade` pasa (7 tests).

- [ ] **Paso 6: commit** (incluye el esqueleto de la tarea 2, con las líneas de modelos y
tests que aún no existen comentadas)

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): esqueleto, parseo de bonificaciones en cascada y fórmula de reposición"
```

---

### Tarea 4: Permisos de edición, condiciones del proveedor e impuestos internos

**Files:**
- Create: `models/commercial_conditions_access.py`, `models/res_partner.py`,
  `models/product_category.py`
- Create (parcial, se completa en tarea 6): `models/product_template.py`
- Create: `tests/common.py`, `tests/test_conditions.py`

- [ ] **Paso 1: `tests/common.py`** (datos compartidos por todos los tests)

```python
from __future__ import annotations

from odoo.tests.common import TransactionCase


class ReplacementCostCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Proveedor Cascada'})
        cls.categ = cls.env['product.category'].create({'name': 'Bebidas Test'})
        cls.product = cls.env['product.product'].create({
            'name': 'Producto Reposición',
            'categ_id': cls.categ.id,
            'standard_price': 800.0,
        })
        cls.template = cls.product.product_tmpl_id

    @classmethod
    def _set_partner_conditions(cls, partner=None, cascade='10+5+3', early=2.0,
                                freight=3.5, perception=1.5):
        (partner or cls.partner).write({
            'purchase_discount_cascade': cascade,
            'purchase_early_payment_pct': early,
            'purchase_freight_pct': freight,
            'purchase_perception_pct': perception,
        })

    @classmethod
    def _add_seller(cls, reference_cost=1000.0, partner=None, **vals):
        return cls.env['product.supplierinfo'].create({
            'partner_id': (partner or cls.partner).id,
            'product_tmpl_id': cls.template.id,
            'price': reference_cost,
            'reference_cost': reference_cost,
            **vals,
        })
```

- [ ] **Paso 2: test que falla** — `tests/test_conditions.py` (primera parte; la parte de
supplierinfo se agrega en la tarea 5)

```python
from __future__ import annotations

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ReplacementCostCommon


@tagged('post_install', '-at_install')
class TestPartnerConditions(ReplacementCostCommon):

    def test_invalid_cascade_on_partner(self):
        with self.assertRaises(ValidationError):
            self.partner.purchase_discount_cascade = '10++5'

    def test_pct_out_of_range(self):
        for field in ('purchase_early_payment_pct', 'purchase_freight_pct',
                      'purchase_perception_pct'):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.partner.write({field: 100.0})
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.partner.write({field: -1.0})

    def test_conditions_are_per_company(self):
        other = self.env['res.company'].create({'name': 'Otra Empresa Test'})
        self.partner.purchase_discount_cascade = '10'
        self.partner.with_company(other).purchase_discount_cascade = '20'
        self.assertEqual(self.partner.purchase_discount_cascade, '10')
        self.assertEqual(self.partner.with_company(other).purchase_discount_cascade, '20')

    def test_internal_tax_from_category(self):
        self.categ.internal_tax_pct = 8.0
        product = self.env['product.product'].create({
            'name': 'Nuevo', 'categ_id': self.categ.id,
        })
        self.assertEqual(product.internal_tax_pct, 8.0)

    def test_internal_tax_manual_override(self):
        self.categ.internal_tax_pct = 8.0
        product = self.env['product.product'].create({
            'name': 'Nuevo', 'categ_id': self.categ.id,
        })
        product.internal_tax_pct = 4.0
        self.assertEqual(product.internal_tax_pct, 4.0)

    def test_internal_tax_follows_category_change(self):
        other_categ = self.env['product.category'].create({
            'name': 'Tabaco Test', 'internal_tax_pct': 12.0,
        })
        self.template.categ_id = other_categ
        self.assertEqual(self.template.internal_tax_pct, 12.0)
```

- [ ] **Paso 3: correr** → falla (campos inexistentes).

- [ ] **Paso 4: `models/commercial_conditions_access.py`**

```python
from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

MANAGER_GROUP = 'purchase.group_purchase_manager'


class CommercialConditionsAccessMixin(models.AbstractModel):
    """Restringe la edición de condiciones comerciales a gerentes de compras.

    Cada modelo que lo hereda declara en `_commercial_condition_fields` qué
    campos protege. La vista usa `can_edit_commercial_conditions` para el
    `readonly`; el servidor valida en create/write.
    """
    _name = 'commercial.conditions.access.mixin'
    _description = 'Permiso de edición de condiciones comerciales'

    _commercial_condition_fields: tuple[str, ...] = ()

    can_edit_commercial_conditions = fields.Boolean(
        compute='_compute_can_edit_commercial_conditions',
    )

    @api.depends_context('uid')
    def _compute_can_edit_commercial_conditions(self) -> None:
        allowed = self.env.user.has_group(MANAGER_GROUP)
        for rec in self:
            rec.can_edit_commercial_conditions = allowed

    def _check_commercial_conditions_access(self, vals_list: list[dict]) -> None:
        if self.env.su or self.env.user.has_group(MANAGER_GROUP):
            return
        touched = {
            field for vals in vals_list for field in vals
            if field in self._commercial_condition_fields
        }
        if touched:
            raise AccessError(_(
                'Sólo los gerentes de compras pueden modificar condiciones '
                'comerciales (%s).', ', '.join(sorted(touched)),
            ))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_commercial_conditions_access(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._check_commercial_conditions_access([vals])
        return super().write(vals)
```

- [ ] **Paso 5: `models/res_partner.py`**

```python
from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..tools import parse_discount_cascade

PARTNER_CONDITION_FIELDS = (
    'purchase_discount_cascade',
    'purchase_early_payment_pct',
    'purchase_freight_pct',
    'purchase_perception_pct',
)


def check_pct_range(records, field_names, label_by_field):
    """Valida 0 ≤ valor < 100 para porcentajes de condiciones comerciales."""
    for rec in records:
        for name in field_names:
            value = rec[name] or 0.0
            if not 0 <= value < 100:
                raise ValidationError(
                    f'{label_by_field[name]}: {value:g} fuera de rango '
                    '(debe ser mayor o igual a 0 y menor que 100).'
                )


def check_cascade(records, field_name):
    for rec in records:
        try:
            parse_discount_cascade(rec[field_name])
        except ValueError as err:
            raise ValidationError(str(err)) from err


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'commercial.conditions.access.mixin']

    _commercial_condition_fields = PARTNER_CONDITION_FIELDS

    purchase_discount_cascade = fields.Char(
        string='Bonificaciones',
        company_dependent=True,
        tracking=True,
        help='Bonificaciones en cascada del proveedor, p. ej. 10+5+3. '
             'Cada una se aplica sobre el neto de la anterior.',
    )
    purchase_early_payment_pct = fields.Float(
        string='Pronto pago (%)', company_dependent=True, tracking=True,
    )
    purchase_freight_pct = fields.Float(
        string='Flete (%)', company_dependent=True, tracking=True,
        help='Costo de flete/logística sobre el neto bonificado.',
    )
    purchase_perception_pct = fields.Float(
        string='Percepción no recuperable (%)', company_dependent=True, tracking=True,
        help='Percepciones (p. ej. IIBB) que no se recuperan, sobre el neto bonificado.',
    )

    @api.constrains('purchase_discount_cascade')
    def _check_purchase_discount_cascade(self) -> None:
        check_cascade(self, 'purchase_discount_cascade')

    @api.constrains('purchase_early_payment_pct', 'purchase_freight_pct',
                    'purchase_perception_pct')
    def _check_purchase_condition_pcts(self) -> None:
        check_pct_range(self, PARTNER_CONDITION_FIELDS[1:], {
            'purchase_early_payment_pct': 'Pronto pago',
            'purchase_freight_pct': 'Flete',
            'purchase_perception_pct': 'Percepción no recuperable',
        })
```

> Verificar: `@api.constrains` sobre campos `company_dependent` se dispara en 19 al
> escribir. Si el test `test_invalid_cascade_on_partner` no levanta, mover la validación a
> `write`/`create` llamando a `check_cascade`/`check_pct_range` después de `super()`.
> Si `tracking=True` en `company_dependent` da error al cargar el módulo, quitarlo y
> anotarlo en el README.

- [ ] **Paso 6: `models/product_category.py`**

```python
from __future__ import annotations

from odoo import api, fields, models

from .res_partner import check_pct_range


class ProductCategory(models.Model):
    _name = 'product.category'
    _inherit = ['product.category', 'commercial.conditions.access.mixin']

    _commercial_condition_fields = ('internal_tax_pct',)

    internal_tax_pct = fields.Float(
        string='Impuestos internos (%)',
        help='Valor por defecto para los productos de esta categoría.',
    )

    @api.constrains('internal_tax_pct')
    def _check_internal_tax_pct(self) -> None:
        check_pct_range(self, ('internal_tax_pct',), {'internal_tax_pct': 'Impuestos internos'})
```

- [ ] **Paso 7: `models/product_template.py`** (primera parte)

```python
from __future__ import annotations

from odoo import api, fields, models

from .res_partner import check_pct_range


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'commercial.conditions.access.mixin']

    _commercial_condition_fields = ('internal_tax_pct',)

    internal_tax_pct = fields.Float(
        string='Impuestos internos (%)',
        compute='_compute_internal_tax_pct',
        store=True,
        readonly=False,
        precompute=True,
        help='Se toma de la categoría al crear el producto o al cambiarlo de '
             'categoría. Se puede modificar a mano.',
    )

    @api.depends('categ_id')
    def _compute_internal_tax_pct(self) -> None:
        for tmpl in self:
            tmpl.internal_tax_pct = tmpl.categ_id.internal_tax_pct

    @api.constrains('internal_tax_pct')
    def _check_internal_tax_pct(self) -> None:
        check_pct_range(self, ('internal_tax_pct',), {'internal_tax_pct': 'Impuestos internos'})
```

> Ojo: el mixin sobreescribe `create`/`write`. Como el cómputo de `internal_tax_pct` no
> pasa por `write`, cambiar la categoría de un producto como usuario no manager **no**
> dispara el `AccessError`. Si en el test de acceso (tarea 10) aparece el error al crear
> un producto como usuario básico, es porque el cliente web manda el valor computado en
> `vals`: en ese caso, en `create` ignorar la clave cuando su valor coincide con el de la
> categoría.

- [ ] **Paso 8: descomentar** en `models/__init__.py` los imports de
`commercial_conditions_access`, `res_partner`, `product_category`, `product_template`, y en
`tests/__init__.py` `test_conditions`.

- [ ] **Paso 9: correr tests** → `TestPartnerConditions` pasa.

- [ ] **Paso 10: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): condiciones comerciales del proveedor e impuestos internos"
```

---

### Tarea 5: Condiciones propias/efectivas y reposición en `product.supplierinfo`

**Files:**
- Create: `models/product_supplierinfo.py`
- Modify: `tests/test_conditions.py` (agregar clase)

- [ ] **Paso 1: test que falla** — agregar al final de `tests/test_conditions.py`:

```python
@tagged('post_install', '-at_install')
class TestSupplierinfoConditions(ReplacementCostCommon):

    def test_inherits_partner_conditions(self):
        self._set_partner_conditions()
        seller = self._add_seller()
        self.assertEqual(seller.effective_discount_cascade, '10+5+3')
        self.assertEqual(seller.effective_early_payment_pct, 2.0)
        self.assertEqual(seller.effective_freight_pct, 3.5)
        self.assertEqual(seller.effective_perception_pct, 1.5)
        self.assertAlmostEqual(seller.discount_equivalent_pct, 17.065, places=6)

    def test_own_conditions_override(self):
        self._set_partner_conditions()
        seller = self._add_seller(
            use_own_conditions=True,
            own_discount_cascade='20',
            own_early_payment_pct=0.0,
            own_freight_pct=0.0,
            own_perception_pct=0.0,
        )
        self.assertEqual(seller.effective_discount_cascade, '20')
        self.assertEqual(seller.effective_freight_pct, 0.0)
        self.assertAlmostEqual(seller.replacement_cost, 800.0, places=6)

    def test_replacement_cost_canonical(self):
        self._set_partner_conditions()
        seller = self._add_seller()
        self.assertAlmostEqual(seller.replacement_cost, 854.2305, places=4)
        self.assertIn('Reposición', seller.replacement_cost_breakdown)
        self.assertIn('10+5+3', seller.replacement_cost_breakdown)

    def test_seller_company_conditions(self):
        """El supplierinfo de otra empresa toma las condiciones de esa empresa."""
        other = self.env['res.company'].create({'name': 'Empresa Seller Test'})
        self.partner.with_company(other).purchase_discount_cascade = '50'
        seller = self._add_seller(company_id=other.id)
        self.assertEqual(seller.effective_discount_cascade, '50')

    def test_invalid_own_cascade(self):
        with self.assertRaises(ValidationError):
            self._add_seller(use_own_conditions=True, own_discount_cascade='x')
```

- [ ] **Paso 2: correr** → falla.

- [ ] **Paso 3: `models/product_supplierinfo.py`**

```python
from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..tools import cascade_equivalent_pct, compute_replacement_cost, parse_discount_cascade
from .res_partner import check_cascade, check_pct_range

OWN_FIELDS = (
    'own_discount_cascade',
    'own_early_payment_pct',
    'own_freight_pct',
    'own_perception_pct',
)


def _fmt(amount: float) -> str:
    """1234.5 → '1.234,50' (formato argentino)."""
    return f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _fmt_pct(value: float) -> str:
    return f'{value:g}'.replace('.', ',')


class ProductSupplierinfo(models.Model):
    _name = 'product.supplierinfo'
    _inherit = ['product.supplierinfo', 'commercial.conditions.access.mixin']

    _commercial_condition_fields = ('use_own_conditions',) + OWN_FIELDS

    use_own_conditions = fields.Boolean(
        string='Condiciones propias',
        help='Si está tildado, usa las condiciones cargadas acá en lugar de las '
             'del proveedor.',
    )
    own_discount_cascade = fields.Char(string='Bonificaciones (propias)')
    own_early_payment_pct = fields.Float(string='Pronto pago % (propio)')
    own_freight_pct = fields.Float(string='Flete % (propio)')
    own_perception_pct = fields.Float(string='Percepción % (propia)')

    effective_discount_cascade = fields.Char(
        string='Bonificaciones', compute='_compute_effective_conditions',
    )
    effective_early_payment_pct = fields.Float(
        string='Pronto pago (%)', compute='_compute_effective_conditions',
    )
    effective_freight_pct = fields.Float(
        string='Flete (%)', compute='_compute_effective_conditions',
    )
    effective_perception_pct = fields.Float(
        string='Percepción (%)', compute='_compute_effective_conditions',
    )
    discount_equivalent_pct = fields.Float(
        string='Bonificación equivalente (%)', digits=(16, 2),
        compute='_compute_effective_conditions',
    )
    replacement_cost = fields.Float(
        string='Costo de reposición', digits='Product Price',
        compute='_compute_replacement_cost',
        help='Costo de referencia de este registro aplicando bonificaciones, pronto '
             'pago, flete, percepción e impuestos internos. En la unidad y moneda '
             'de esta ficha.',
    )
    replacement_cost_breakdown = fields.Char(
        string='Desglose', compute='_compute_replacement_cost',
    )

    @api.depends(
        'use_own_conditions', *OWN_FIELDS, 'company_id',
        'partner_id.commercial_partner_id.purchase_discount_cascade',
        'partner_id.commercial_partner_id.purchase_early_payment_pct',
        'partner_id.commercial_partner_id.purchase_freight_pct',
        'partner_id.commercial_partner_id.purchase_perception_pct',
    )
    @api.depends_context('company')
    def _compute_effective_conditions(self) -> None:
        for rec in self:
            if rec.use_own_conditions:
                cascade = rec.own_discount_cascade
                early = rec.own_early_payment_pct
                freight = rec.own_freight_pct
                perception = rec.own_perception_pct
            else:
                partner = rec.partner_id.commercial_partner_id.with_company(
                    rec.company_id or self.env.company
                )
                cascade = partner.purchase_discount_cascade
                early = partner.purchase_early_payment_pct
                freight = partner.purchase_freight_pct
                perception = partner.purchase_perception_pct
            rec.effective_discount_cascade = cascade or False
            rec.effective_early_payment_pct = early
            rec.effective_freight_pct = freight
            rec.effective_perception_pct = perception
            try:
                values = parse_discount_cascade(cascade)
            except ValueError:
                values = []
            rec.discount_equivalent_pct = cascade_equivalent_pct(values)

    @api.depends(
        'reference_cost', 'product_tmpl_id.internal_tax_pct',
        'discount_equivalent_pct', 'effective_early_payment_pct',
        'effective_freight_pct', 'effective_perception_pct',
    )
    @api.depends_context('company')
    def _compute_replacement_cost(self) -> None:
        for rec in self:
            internal = rec.product_tmpl_id.internal_tax_pct
            net, replacement = compute_replacement_cost(
                rec.reference_cost,
                rec.discount_equivalent_pct,
                rec.effective_early_payment_pct,
                rec.effective_freight_pct,
                rec.effective_perception_pct,
                internal,
            )
            rec.replacement_cost = replacement
            if not rec.reference_cost:
                rec.replacement_cost_breakdown = False
                continue
            extras = []
            if rec.effective_early_payment_pct:
                extras.append(f'−{_fmt_pct(rec.effective_early_payment_pct)}% PP')
            if rec.effective_freight_pct:
                extras.append(f'+{_fmt_pct(rec.effective_freight_pct)}% flete')
            if rec.effective_perception_pct:
                extras.append(f'+{_fmt_pct(rec.effective_perception_pct)}% percep.')
            if internal:
                extras.append(f'+{_fmt_pct(internal)}% internos')
            cascade = f' ({rec.effective_discount_cascade})' if rec.effective_discount_cascade else ''
            extras_txt = f' ({" ".join(extras)})' if extras else ''
            rec.replacement_cost_breakdown = (
                f'Lista {_fmt(rec.reference_cost)} → Neto {_fmt(net)}{cascade}'
                f' → Reposición {_fmt(replacement)}{extras_txt}'
            )

    @api.constrains('own_discount_cascade')
    def _check_own_discount_cascade(self) -> None:
        check_cascade(self, 'own_discount_cascade')

    @api.constrains('own_early_payment_pct', 'own_freight_pct', 'own_perception_pct')
    def _check_own_pcts(self) -> None:
        check_pct_range(self, OWN_FIELDS[1:], {
            'own_early_payment_pct': 'Pronto pago',
            'own_freight_pct': 'Flete',
            'own_perception_pct': 'Percepción no recuperable',
        })
```

> `ValidationError` se importa por si el agente necesita mover la validación a `write`
> (ver nota de la tarea 4); si no se usa, quitar el import.

- [ ] **Paso 4: descomentar** `product_supplierinfo` en `models/__init__.py`.

- [ ] **Paso 5: correr tests** → `TestSupplierinfoConditions` pasa. Si
`test_inherits_partner_conditions` falla por cache (el valor del partner cambió después de
leer el seller), revisar las `depends`; no agregar `invalidate_all()` al test.

- [ ] **Paso 6: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): condiciones propias y costo de reposición por ficha de proveedor"
```

---

### Tarea 6: Reposición en el producto y helper para ventas

**Files:**
- Modify: `models/product_template.py`
- Create: `models/product_product.py`
- Test: `tests/test_replacement_cost.py`

- [ ] **Paso 1: test que falla** — `tests/test_replacement_cost.py`

```python
from __future__ import annotations

from odoo import fields
from odoo.tests import tagged

from .common import ReplacementCostCommon


@tagged('post_install', '-at_install')
class TestTemplateReplacementCost(ReplacementCostCommon):

    def test_canonical_example(self):
        self._set_partner_conditions()
        self._add_seller()
        self.assertAlmostEqual(self.template.reference_cost, 1000.0)
        self.assertAlmostEqual(self.template.net_purchase_cost, 829.35, places=4)
        self.assertAlmostEqual(self.template.replacement_cost, 854.2305, places=4)

    def test_internal_tax_adds_on_net(self):
        self._set_partner_conditions(early=0, freight=0, perception=0)
        self.template.internal_tax_pct = 10.0
        self._add_seller()
        self.assertAlmostEqual(self.template.replacement_cost, 829.35 * 1.10, places=4)

    def test_no_seller_is_zero(self):
        self.assertEqual(self.template.replacement_cost, 0.0)
        self.assertEqual(self.template.net_purchase_cost, 0.0)

    def test_uom_pack(self):
        """Lista por pack de 24 → reposición por unidad."""
        self._set_partner_conditions(cascade='', early=0, freight=0, perception=0)
        uom_unit = self.env.ref('uom.product_uom_unit')
        pack = self.env['uom.uom'].create({
            'name': 'Pack x24 Test',
            'relative_factor': 24.0,
            'relative_uom_id': uom_unit.id,
        })
        self._add_seller(reference_cost=2400.0, product_uom_id=pack.id)
        self.assertAlmostEqual(self.template.replacement_cost, 100.0, places=4)

    def test_currency_usd(self):
        self._set_partner_conditions(cascade='', early=0, freight=0, perception=0)
        usd = self.env.ref('base.USD')
        usd.active = True
        company_currency = self.env.company.currency_id
        if company_currency == usd:
            self.skipTest('La empresa de test ya usa USD')
        self.env['res.currency.rate'].create({
            'currency_id': usd.id,
            'company_id': self.env.company.id,
            'name': fields.Date.today(),
            # 1 moneda-empresa = 0.001 USD → 1 USD = 1000 moneda-empresa
            'rate': 0.001,
        })
        self._add_seller(reference_cost=2.0, currency_id=usd.id)
        self.assertAlmostEqual(self.template.replacement_cost, 2000.0, places=2)

    def test_get_replacement_cost_for_fallback(self):
        cost, is_fallback = self.product._get_replacement_cost_for(
            self.env.company, self.product.uom_id, self.env.company.currency_id,
            fields.Date.today(),
        )
        self.assertTrue(is_fallback)
        self.assertEqual(cost, 800.0)

    def test_get_replacement_cost_for_uom(self):
        self._set_partner_conditions()
        self._add_seller()
        dozen = self.env.ref('uom.product_uom_dozen')
        cost, is_fallback = self.product._get_replacement_cost_for(
            self.env.company, dozen, self.env.company.currency_id, fields.Date.today(),
        )
        self.assertFalse(is_fallback)
        self.assertAlmostEqual(cost, 854.2305 * 12, places=3)
```

> Si el test de UoM falla porque en 19 los campos de `uom.uom` se llaman distinto,
> copiar la forma de crear la UoM desde
> `alpardata_purchase_reference_cost/tests/test_purchase_line_price.py` (ya resolvió esto
> para 19).

- [ ] **Paso 2: correr** → falla.

- [ ] **Paso 3: agregar a `models/product_template.py`** (debajo de lo existente):

```python
    replacement_cost = fields.Float(
        string='Costo de reposición',
        digits='Product Price',
        compute='_compute_replacement_cost',
        help='Costo de referencia del proveedor vigente aplicando bonificaciones en '
             'cascada, pronto pago, flete, percepción e impuestos internos.',
    )
    net_purchase_cost = fields.Float(
        string='Neto bonificado',
        digits='Product Price',
        compute='_compute_replacement_cost',
        help='Costo de referencia menos bonificaciones en cascada (sin adicionales).',
    )

    @api.depends(
        'reference_cost', 'internal_tax_pct',
        'seller_ids.discount_equivalent_pct',
        'seller_ids.effective_early_payment_pct',
        'seller_ids.effective_freight_pct',
        'seller_ids.effective_perception_pct',
    )
    @api.depends_context('company')
    def _compute_replacement_cost(self) -> None:
        """Aplica la fórmula sobre `reference_cost`, que ya viene convertido a la
        UoM del producto y a la moneda de la empresa, usando las condiciones del
        mismo proveedor que eligió el resolver de `reference_cost`."""
        for tmpl in self:
            seller = tmpl._get_reference_cost_seller()
            if not seller or not tmpl.reference_cost:
                tmpl.replacement_cost = 0.0
                tmpl.net_purchase_cost = 0.0
                continue
            net, replacement = compute_replacement_cost(
                tmpl.reference_cost,
                seller.discount_equivalent_pct,
                seller.effective_early_payment_pct,
                seller.effective_freight_pct,
                seller.effective_perception_pct,
                tmpl.internal_tax_pct,
            )
            tmpl.net_purchase_cost = net
            tmpl.replacement_cost = replacement
```

y al principio del archivo: `from ..tools import compute_replacement_cost`.

- [ ] **Paso 4: `models/product_product.py`**

```python
from __future__ import annotations

from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _get_replacement_cost_for(self, company, uom, currency, date) -> tuple[float, bool]:
        """Costo de reposición unitario en `uom` y `currency`.

        Devuelve (costo, is_fallback). Si el producto no tiene costo de
        reposición usa `standard_price` (mismo criterio que las listas de
        precios) e informa is_fallback=True.
        """
        self.ensure_one()
        product = self.with_company(company)
        cost = product.replacement_cost
        is_fallback = not cost
        if is_fallback:
            cost = product.standard_price
        if uom and product.uom_id and uom != product.uom_id:
            cost = product.uom_id._compute_price(cost, uom)
        if currency and currency != company.currency_id:
            cost = company.currency_id._convert(cost, currency, company, date, round=False)
        return cost, is_fallback
```

- [ ] **Paso 5: descomentar** `product_product` en `models/__init__.py` y
`test_replacement_cost` en `tests/__init__.py`.

- [ ] **Paso 6: correr tests** → pasan.

- [ ] **Paso 7: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): costo de reposición y neto bonificado en el producto"
```

---

### Tarea 7: Base "Costo de Reposición" en listas de precios

**Files:**
- Create: `models/product_pricelist.py`
- Test: `tests/test_pricelist.py`

- [ ] **Paso 1: test que falla** — `tests/test_pricelist.py`

```python
from __future__ import annotations

from odoo.tests import tagged

from .common import ReplacementCostCommon


@tagged('post_install', '-at_install')
class TestReplacementCostPricelist(ReplacementCostCommon):

    def _pricelist(self, markup_pct):
        return self.env['product.pricelist'].create({
            'name': 'Lista Reposición Test',
            'currency_id': self.env.company.currency_id.id,
            'item_ids': [(0, 0, {
                'applied_on': '3_global',
                'compute_price': 'formula',
                'base': 'replacement_cost',
                # price_markup: recargo sobre la base (Odoo 17+)
                'price_markup': markup_pct,
            })],
        })

    def test_price_from_replacement_cost(self):
        self._set_partner_conditions()
        self._add_seller()
        pricelist = self._pricelist(40.0)
        price = pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 854.2305 * 1.40, places=2)

    def test_fallback_to_standard_price(self):
        pricelist = self._pricelist(0.0)
        price = pricelist._get_product_price(self.product, 1.0)
        self.assertAlmostEqual(price, 800.0, places=2)

    def test_reference_cost_base_unchanged(self):
        """La base existente sigue devolviendo la lista pura."""
        self._set_partner_conditions()
        self._add_seller()
        pricelist = self.env['product.pricelist'].create({
            'name': 'Lista Referencia Test',
            'item_ids': [(0, 0, {
                'applied_on': '3_global',
                'compute_price': 'formula',
                'base': 'reference_cost',
            })],
        })
        self.assertAlmostEqual(pricelist._get_product_price(self.product, 1.0), 1000.0, places=2)
```

> Verificar en `odoo-19.0/addons/product/models/product_pricelist_item.py` el nombre del
> campo de recargo (`price_markup` en 19; en versiones previas se usaba `price_discount`
> negativo). Ajustar el test al nombre real.

- [ ] **Paso 2: correr** → falla (`base` no admite `replacement_cost`).

- [ ] **Paso 3: `models/product_pricelist.py`**

```python
from __future__ import annotations

import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    base = fields.Selection(
        selection_add=[('replacement_cost', 'Costo de Reposición')],
        ondelete={'replacement_cost': 'set default'},
    )

    def _compute_base_price(self, product, quantity, uom, date, currency, **kwargs) -> float:
        if self.base != 'replacement_cost':
            return super()._compute_base_price(product, quantity, uom, date, currency, **kwargs)
        currency.ensure_one()
        cost = product.replacement_cost
        if not cost:
            _logger.warning(
                'Producto "%s" sin costo de reposición. Se usa el costo estándar '
                'para la lista de precios.', product.display_name,
            )
            cost = product.standard_price
        return self._convert_commercial_cost(product, cost, uom, date, currency)

    def _get_price_label_base_str(self) -> str:
        self.ensure_one()
        if self.base == 'replacement_cost':
            return _('costo de reposición')
        return super()._get_price_label_base_str()
```

- [ ] **Paso 4: descomentar** `product_pricelist` y `test_pricelist`.

- [ ] **Paso 5: correr tests** → pasan.

- [ ] **Paso 6: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): base Costo de Reposición en listas de precios"
```

---

### Tarea 8: Bonificaciones en cascada en órdenes de compra

**Files:**
- Create: `models/purchase_order_line.py`, `models/purchase_order.py`
- Test: `tests/test_purchase_order.py`

- [ ] **Paso 1: test que falla** — `tests/test_purchase_order.py`

```python
from __future__ import annotations

from odoo.tests import tagged

from .common import ReplacementCostCommon


@tagged('post_install', '-at_install')
class TestPurchaseOrderCascade(ReplacementCostCommon):

    def _order(self):
        return self.env['purchase.order'].create({'partner_id': self.partner.id})

    def _line(self, po):
        return self.env['purchase.order.line'].create({
            'order_id': po.id,
            'product_id': self.product.id,
            'product_qty': 1.0,
        })

    def test_manual_line_gets_cascade(self):
        self._set_partner_conditions()
        self._add_seller()
        line = self._line(self._order())
        self.assertEqual(line.price_unit, 1000.0)
        self.assertAlmostEqual(line.discount, 17.065, places=2)
        self.assertEqual(line.discount_cascade, '10+5+3')

    def test_without_cascade_uses_supplierinfo_discount(self):
        self._set_partner_conditions(cascade='')
        self._add_seller(discount=7.0)
        line = self._line(self._order())
        self.assertEqual(line.discount, 7.0)
        self.assertFalse(line.discount_cascade)

    def test_manual_price_not_touched(self):
        self._set_partner_conditions()
        self._add_seller()
        line = self._line(self._order())
        line.write({'price_unit': 900.0, 'discount': 0.0})
        line.product_qty = 2.0
        self.assertEqual(line.price_unit, 900.0)
        self.assertEqual(line.discount, 0.0)

    def test_catalog_path(self):
        self._set_partner_conditions()
        self._add_seller()
        po = self._order()
        po._update_order_line_info(self.product.id, 1.0)
        line = po.order_line.filtered(lambda l: l.product_id == self.product)
        self.assertAlmostEqual(line.discount, 17.065, places=2)
        self.assertEqual(line.discount_cascade, '10+5+3')

    def test_replenishment_path(self):
        self._set_partner_conditions()
        self._add_seller()
        po = self._order()
        vals = self.env['purchase.order.line']._prepare_purchase_order_line(
            self.product, 1.0, self.product.uom_id, self.env.company, self.partner, po,
        )
        self.assertAlmostEqual(vals['discount'], 17.065, places=2)
        self.assertEqual(vals['discount_cascade'], '10+5+3')
```

- [ ] **Paso 2: correr** → falla.

- [ ] **Paso 3: `models/purchase_order_line.py`**

```python
from __future__ import annotations

from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    discount_cascade = fields.Char(
        string='Bonificaciones',
        readonly=True,
        copy=True,
        help='Bonificaciones en cascada negociadas con el proveedor al cargar la '
             'línea. El % de descuento de la línea es su equivalente.',
    )

    @api.model
    def _get_cascade_seller(self, product, company, partner):
        """Ficha del proveedor de la orden, con la misma jerarquía de empresas
        que el costo de referencia."""
        if not product or not company or not partner:
            return self.env['product.supplierinfo']
        return product.product_tmpl_id.with_company(company)._get_reference_cost_seller(
            partner=partner,
        )

    def _apply_discount_cascade(self) -> None:
        """Pone el descuento equivalente de la cascada del proveedor.

        No toca líneas con precio puesto a mano ni líneas facturadas. Sin
        cascada deja el descuento que calculó el core (`supplierinfo.discount`).
        """
        for line in self:
            if not line.product_id or line.invoice_lines or not line.company_id:
                continue
            if line.technical_price_unit != line.price_unit:
                continue
            seller = self._get_cascade_seller(
                line.product_id, line.company_id,
                line.order_id.partner_id or line.partner_id,
            )
            cascade = seller.effective_discount_cascade if seller else False
            if cascade:
                line.discount = seller.discount_equivalent_pct
                line.discount_cascade = cascade
            else:
                line.discount_cascade = False

    def _compute_price_unit_and_date_planned_and_name(self):
        super()._compute_price_unit_and_date_planned_and_name()
        self._apply_discount_cascade()

    @api.model
    def _prepare_purchase_order_line(self, product_id, product_qty, product_uom,
                                     company_id, partner_id, po):
        vals = super()._prepare_purchase_order_line(
            product_id, product_qty, product_uom, company_id, partner_id, po,
        )
        seller = self._get_cascade_seller(product_id, company_id, partner_id)
        if seller and seller.effective_discount_cascade:
            vals['discount'] = seller.discount_equivalent_pct
            vals['discount_cascade'] = seller.effective_discount_cascade
        return vals
```

- [ ] **Paso 4: `models/purchase_order.py`**

```python
from __future__ import annotations

from odoo import models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _update_order_line_info(self, product_id, quantity, *, section_id=False, **kwargs):
        """Alta desde el catálogo: aplica la cascada después de que el módulo
        base fija el precio de referencia. Busca la línea igual que el base
        (producto + sección)."""
        price = super()._update_order_line_info(
            product_id, quantity, section_id=section_id, **kwargs
        )
        line = self.order_line.filtered(
            lambda pol: pol.product_id.id == product_id
            and pol.get_parent_section_line().id == section_id
        )[:1]
        if line:
            line._apply_discount_cascade()
            return line.price_unit_discounted
        return price
```

- [ ] **Paso 5: descomentar** `purchase_order_line`, `purchase_order`, `test_purchase_order`.

- [ ] **Paso 6: correr tests** → pasan. Correr también los del base (`test_purchase_line_price`)
para confirmar que no se rompió el precio de referencia.

- [ ] **Paso 7: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): bonificaciones en cascada como descuento en órdenes de compra"
```

---

### Tarea 9: Semáforo de divergencia contra el neto bonificado

**Files:**
- Modify: `models/product_template.py`
- Test: `tests/test_divergence.py`

- [ ] **Paso 1: test que falla** — `tests/test_divergence.py`

```python
from __future__ import annotations

from odoo.tests import tagged

from .common import ReplacementCostCommon


@tagged('post_install', '-at_install')
class TestDivergenceNetCost(ReplacementCostCommon):

    def test_avco_equal_to_net_is_ok(self):
        self._set_partner_conditions()
        self._add_seller()
        self.template.standard_price = 829.35
        self.assertEqual(self.template.cost_divergence_alert, 'ok')
        self.assertAlmostEqual(self.template.cost_divergence_pct, 0.0, places=2)

    def test_without_cascade_compares_to_list(self):
        self._set_partner_conditions(cascade='')
        self._add_seller()
        self.template.standard_price = 1000.0
        self.assertEqual(self.template.cost_divergence_alert, 'ok')
```

- [ ] **Paso 2: correr** → `test_avco_equal_to_net_is_ok` falla (hoy compara contra 1000 →
17 % → `warning`).

- [ ] **Paso 3: agregar a `models/product_template.py`**

```python
    def _get_divergence_base_cost(self) -> float:
        """El AVCO sale de facturas ya bonificadas: se compara contra el neto
        bonificado, no contra la lista."""
        self.ensure_one()
        return self.net_purchase_cost or super()._get_divergence_base_cost()
```

Y agregar `'net_purchase_cost'` al `@api.depends` del compute de divergencia: como el
compute vive en el base, en este módulo se re-declara:

```python
    @api.depends('standard_price', 'reference_cost', 'net_purchase_cost')
    def _compute_cost_divergence(self) -> None:
        return super()._compute_cost_divergence()
```

- [ ] **Paso 4: descomentar** `test_divergence`. **Correr tests** → pasan.

- [ ] **Paso 5: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): semáforo de divergencia contra el neto bonificado"
```

---

### Tarea 10: Permisos (servidor)

**Files:** Test: `tests/test_access.py`

- [ ] **Paso 1: test** — `tests/test_access.py`

```python
from __future__ import annotations

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import ReplacementCostCommon


@tagged('post_install', '-at_install')
class TestCommercialConditionsAccess(ReplacementCostCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.buyer = new_test_user(cls.env, login='buyer_rc', groups='purchase.group_purchase_user')
        cls.manager = new_test_user(cls.env, login='manager_rc', groups='purchase.group_purchase_manager')

    def test_buyer_cannot_edit_partner_conditions(self):
        with self.assertRaises(AccessError):
            self.partner.with_user(self.buyer).purchase_discount_cascade = '10'

    def test_buyer_can_edit_other_partner_fields(self):
        self.partner.with_user(self.buyer).write({'phone': '1234'})

    def test_manager_can_edit(self):
        self.partner.with_user(self.manager).purchase_discount_cascade = '10'
        self.assertEqual(self.partner.purchase_discount_cascade, '10')

    def test_buyer_cannot_set_own_conditions(self):
        seller = self._add_seller()
        with self.assertRaises(AccessError):
            seller.with_user(self.buyer).use_own_conditions = True

    def test_buyer_can_create_product_in_taxed_category(self):
        """El valor computado desde la categoría no cuenta como edición manual."""
        self.categ.internal_tax_pct = 8.0
        product = self.env['product.template'].with_user(self.buyer).create({
            'name': 'Creado por comprador', 'categ_id': self.categ.id,
        })
        self.assertEqual(product.internal_tax_pct, 8.0)

    def test_can_edit_flag(self):
        self.assertFalse(self.partner.with_user(self.buyer).can_edit_commercial_conditions)
        self.assertTrue(self.partner.with_user(self.manager).can_edit_commercial_conditions)
```

> Si `new_test_user` del comprador no puede escribir `res.partner` por ACL propias de
> Odoo, darle también `base.group_partner_manager` en `groups` (separados por coma).

- [ ] **Paso 2: descomentar** `test_access`. **Correr** → pasan (la lógica ya existe desde
la tarea 4). Si algo falla, corregir el mixin, no el test.

- [ ] **Paso 3: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "test(purchase_replacement_cost): permisos de edición de condiciones comerciales"
```

---

### Tarea 11: Vistas

**Files:** Create los 5 XML de `views/`.

- [ ] **Paso 1: `views/res_partner_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_partner_form_commercial_conditions" model="ir.ui.view">
        <field name="name">res.partner.form.commercial.conditions</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="purchase.view_partner_property_form"/>
        <field name="arch" type="xml">
            <xpath expr="//group[@name='purchase']" position="after">
                <group name="commercial_conditions" string="Condiciones comerciales"
                       groups="purchase.group_purchase_user">
                    <field name="can_edit_commercial_conditions" invisible="1"/>
                    <field name="purchase_discount_cascade" placeholder="10+5+3"
                           readonly="not can_edit_commercial_conditions"/>
                    <field name="purchase_early_payment_pct"
                           readonly="not can_edit_commercial_conditions"/>
                    <field name="purchase_freight_pct"
                           readonly="not can_edit_commercial_conditions"/>
                    <field name="purchase_perception_pct"
                           readonly="not can_edit_commercial_conditions"/>
                </group>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 2: `views/product_category_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_category_form_internal_tax" model="ir.ui.view">
        <field name="name">product.category.form.internal.tax</field>
        <field name="model">product.category</field>
        <field name="inherit_id" ref="product.product_category_form_view"/>
        <field name="arch" type="xml">
            <xpath expr="//group[@name='first']" position="inside">
                <field name="can_edit_commercial_conditions" invisible="1"/>
                <field name="internal_tax_pct"
                       readonly="not can_edit_commercial_conditions"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 3: `views/product_supplierinfo_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="product_supplierinfo_form_replacement_cost" model="ir.ui.view">
        <field name="name">product.supplierinfo.form.replacement.cost</field>
        <field name="model">product.supplierinfo</field>
        <field name="inherit_id" ref="product.product_supplierinfo_form_view"/>
        <field name="arch" type="xml">
            <xpath expr="//sheet/group" position="after">
                <group name="replacement_cost" string="Costo de reposición"
                       groups="purchase.group_purchase_user">
                    <group>
                        <field name="can_edit_commercial_conditions" invisible="1"/>
                        <field name="use_own_conditions"
                               readonly="not can_edit_commercial_conditions"/>
                        <field name="own_discount_cascade" placeholder="10+5+3"
                               invisible="not use_own_conditions"
                               readonly="not can_edit_commercial_conditions"/>
                        <field name="own_early_payment_pct" invisible="not use_own_conditions"
                               readonly="not can_edit_commercial_conditions"/>
                        <field name="own_freight_pct" invisible="not use_own_conditions"
                               readonly="not can_edit_commercial_conditions"/>
                        <field name="own_perception_pct" invisible="not use_own_conditions"
                               readonly="not can_edit_commercial_conditions"/>
                        <field name="effective_discount_cascade" invisible="use_own_conditions"/>
                        <field name="effective_early_payment_pct" invisible="use_own_conditions"/>
                        <field name="effective_freight_pct" invisible="use_own_conditions"/>
                        <field name="effective_perception_pct" invisible="use_own_conditions"/>
                    </group>
                    <group>
                        <field name="discount_equivalent_pct"/>
                        <field name="replacement_cost"/>
                        <field name="replacement_cost_breakdown" colspan="2" nolabel="1"/>
                    </group>
                </group>
            </xpath>
        </field>
    </record>

    <record id="product_supplierinfo_list_replacement_cost" model="ir.ui.view">
        <field name="name">product.supplierinfo.list.replacement.cost</field>
        <field name="model">product.supplierinfo</field>
        <field name="inherit_id" ref="purchase.product_supplierinfo_tree_view2"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='price']" position="after">
                <field name="effective_discount_cascade" string="Bonif." optional="show"/>
                <field name="discount_equivalent_pct" string="Bonif. eq. %" optional="hide"/>
                <field name="replacement_cost" string="Reposición" optional="show"
                       groups="purchase.group_purchase_manager"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 4: `views/product_template_views.xml`** (hereda la pestaña del base)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_product_template_form_replacement_cost" model="ir.ui.view">
        <field name="name">product.template.form.replacement.cost</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="alpardata_purchase_reference_cost.view_product_template_form_reference_cost"/>
        <field name="arch" type="xml">
            <xpath expr="//page[@name='reference_cost_tab']//field[@name='reference_cost']" position="after">
                <field name="net_purchase_cost" widget="monetary"
                       options="{'currency_field': 'cost_currency_id'}" readonly="True"/>
                <field name="replacement_cost" widget="monetary"
                       options="{'currency_field': 'cost_currency_id'}" readonly="True"/>
                <field name="can_edit_commercial_conditions" invisible="1"/>
                <field name="internal_tax_pct"
                       readonly="not can_edit_commercial_conditions"/>
            </xpath>
        </field>
    </record>

    <record id="product_template_list_replacement_cost" model="ir.ui.view">
        <field name="name">product.template.list.replacement.cost</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product.product_template_tree_view"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='standard_price']" position="after">
                <field name="replacement_cost" optional="hide"
                       groups="purchase.group_purchase_manager"/>
            </xpath>
        </field>
    </record>
</odoo>
```

> El spec menciona la pestaña Compra para `internal_tax_pct`; se ubica en la pestaña
> "Costo de Referencia" del base (sólo visible para gerentes de compras), que es quien lo
> edita. Es intencional.

- [ ] **Paso 5: `views/purchase_order_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="purchase_order_form_discount_cascade" model="ir.ui.view">
        <field name="name">purchase.order.form.discount.cascade</field>
        <field name="model">purchase.order</field>
        <field name="inherit_id" ref="purchase.purchase_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='order_line']/list/field[@name='discount']" position="before">
                <field name="discount_cascade" optional="hide"/>
            </xpath>
        </field>
    </record>
</odoo>
```

> Si el xpath no matchea (la lista de líneas puede estar anidada distinto), abrir
> `odoo-19.0/addons/purchase/views/purchase_views.xml` cerca de la línea 293 y ajustar a
> `//field[@name='order_line']//list//field[@name='discount']`.

- [ ] **Paso 6: agregar las vistas al manifest**:

```python
    'data': [
        'views/res_partner_views.xml',
        'views/product_category_views.xml',
        'views/product_supplierinfo_views.xml',
        'views/product_template_views.xml',
        'views/purchase_order_views.xml',
    ],
```

- [ ] **Paso 7: validar XML** y actualizar el módulo:

```bash
odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_purchase_replacement_cost --stop-after-init
```
Esperado: sin `ParseError` ni `ValidationError` de vistas en el log.

- [ ] **Paso 8: prueba manual** (anotar resultado en el PR): proveedor con `10+5+3`,
producto con lista 1.000 → ficha muestra reposición; OC nueva con ese proveedor → línea
con 17,07 % y columna Bonificaciones `10+5+3`.

- [ ] **Paso 9: commit**

```bash
git add alpardata_purchase_replacement_cost
git commit -m "feat(purchase_replacement_cost): vistas de condiciones comerciales y costo de reposición"
```

---

### Tarea 12: README y corrida completa

**Files:** Create `alpardata_purchase_replacement_cost/README.md`.

- [ ] **Paso 1: README** con: qué resuelve, fórmula y ejemplo canónico, dónde se cargan las
condiciones (proveedor por empresa, excepción por ficha, internos por categoría/producto),
permisos (sólo gerentes de compras editan), cómo crear una regla de lista con base "Costo
de Reposición", qué pasa en la OC, y limitaciones (sin recargos negativos; pronto pago,
flete, percepción e internos no van a la OC).

- [ ] **Paso 2: corrida completa** de ambos módulos (comando de Convenciones). Esperado:
0 fallas, 0 errores.

- [ ] **Paso 3: commit y PR**

```bash
git add alpardata_purchase_replacement_cost/README.md
git commit -m "docs(purchase_replacement_cost): README"
git push -u origin feat/replacement-cost
```
Abrir PR contra `19.0` con el resumen, el resultado de los tests y la prueba manual.
