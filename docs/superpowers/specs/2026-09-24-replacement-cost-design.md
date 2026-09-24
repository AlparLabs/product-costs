# Costo de reposición desglosado

> **OBSOLETO (2026-09-24):** reemplazado por `specs/2026-09-24-adhoc-replenishment-cost-design.md`
> (costo de reposición sobre `product_replenishment_cost` de Adhoc). Se conserva como referencia.

**Fecha:** 2026-09-24
**Módulo nuevo:** `alpardata_purchase_replacement_cost`
**Depende de:** `alpardata_purchase_reference_cost` (refactors chicos, sin cambio de comportamiento)
**Rama objetivo:** `19.0`
**Roadmap:** punto 1 de 5 (ver `2026-09-24-commercial-cost-roadmap.md`)

## Problema

`alpardata_purchase_reference_cost` separa el costo contable (AVCO) del costo comercial,
pero el `reference_cost` es **un solo número**: el precio de lista del proveedor. En
Argentina el costo real de la mercadería puesta en el depósito difiere de la lista por:

- **Bonificaciones en cascada** (`10+5+3`): cada una se aplica sobre el neto de la
  anterior, no se suman. Odoo tiene un único `discount`.
- **Pronto pago**: descuento financiero por condición de pago.
- **Flete / logística**: costo de traer la mercadería.
- **Impuestos internos** (bebidas, tabaco, electrónica) y **percepciones de IIBB no
  recuperables**.

Con la lista pura, el margen que calculan las listas de precios de venta es irreal:
optimista si hay flete/percepciones, pesimista si hay bonificaciones.

## Objetivo

Un `replacement_cost` (Costo de Reposición) por producto, calculado con una fórmula
auditable, disponible como base de listas de precios, y bonificaciones en cascada
aplicadas automáticamente como descuento en las órdenes de compra.

## Fórmula

```
neto        = lista × (1 − b1/100) × (1 − b2/100) × …
reposición  = neto × (1 − pronto_pago/100 + flete/100 + percepción/100 + internos/100)
```

Todos los adicionales se calculan **sobre el neto bonificado** (la base sobre la que
factura el proveedor). No se componen entre sí: más fácil de auditar y de explicar.

**Ejemplo canónico** (se usa en los tests): lista 1.000,00; bonificaciones `10+5+3`;
pronto pago 2; flete 3,5; percepción 1,5; internos 0.

- equivalente bonificación = 1 − 0,9 × 0,95 × 0,97 = 17,065 % → se muestra 17,07 %
- neto = 1.000 × 0,82935 = 829,35
- reposición = 829,35 × (1 − 0,02 + 0,035 + 0,015) = 829,35 × 1,03 = **854,2305**

## Modelo de datos

### `res.partner` (proveedor)

Campos `company_dependent=True` (cada empresa del grupo negocia sus condiciones),
`tracking=True`:

| Campo | Tipo | Etiqueta |
|---|---|---|
| `purchase_discount_cascade` | Char | Bonificaciones |
| `purchase_early_payment_pct` | Float | Pronto pago (%) |
| `purchase_freight_pct` | Float | Flete (%) |
| `purchase_perception_pct` | Float | Percepción no recuperable (%) |

> Nota: `tracking=True` sobre campos `company_dependent` registra el cambio de la
> empresa activa. Verificar en la implementación que funcione en 19; si no, se omite
> el tracking y se documenta.

### `product.supplierinfo`

- `use_own_conditions` (Boolean, "Condiciones propias").
- `own_discount_cascade`, `own_early_payment_pct`, `own_freight_pct`,
  `own_perception_pct`: mismos tipos; solo se usan si `use_own_conditions`.
- Computados no almacenados, `depends_context('company')`:
  - `effective_discount_cascade`, `effective_early_payment_pct`,
    `effective_freight_pct`, `effective_perception_pct` — propios o del proveedor
    (`partner_id.commercial_partner_id`, con la empresa del supplierinfo si tiene, si no
    la activa).
  - `discount_equivalent_pct` — equivalente de la cascada efectiva.
  - `replacement_cost` — `reference_cost` del registro aplicando la fórmula (en la UoM y
    moneda del supplierinfo, sin conversión).
  - `replacement_cost_breakdown` (Char) — texto de auditoría, p. ej.
    `Lista 1.000,00 → Neto 829,35 (10+5+3) → Reposición 854,23 (−2% PP +3,5% flete +1,5% percep.)`.

### `product.category`

- `internal_tax_pct` (Float, "Impuestos internos (%)").

### `product.template`

- `internal_tax_pct` (Float) — computado **almacenado y editable**
  (`store=True, readonly=False`), `depends('categ_id')`: toma el valor de la categoría al
  crear o al cambiar de categoría; se puede pisar a mano.
- `replacement_cost` (Float, no almacenado, `depends_context('company')`):
  usa el **mismo resolver** que `reference_cost`
  (`_get_reference_cost_seller()`) y aplica el factor sobre `reference_cost`, que ya
  viene convertido a UoM del producto y moneda de la empresa:
  `replacement_cost = reference_cost × (1 − eq_bonif) × (1 − pp + flete + percep + internos)`.
- `net_purchase_cost` (Float, no almacenado): `reference_cost × (1 − eq_bonif)`.
  Se usa para el semáforo de divergencia.

### `product.product`

- `_get_replacement_cost_for(company, uom, currency, date) -> tuple[float, bool]`:
  `product_tmpl_id.with_company(company).replacement_cost` convertido de la UoM del
  producto a `uom` y de la moneda de la empresa a `currency` (con
  `_convert_commercial_cost`-equivalente: `company.currency_id._convert(..., date)`).
  Si la reposición es 0 devuelve `standard_price` convertido y `True` (fallback). Lo
  consume el punto 5.

## Parseo de la cascada

Función pura `parse_discount_cascade(text) -> list[float]` en `tools/discount_cascade.py`,
y `cascade_equivalent_pct(values) -> float`.

- Vacío / `False` / solo espacios → `[]` → equivalente 0.
- Separador `+`; espacios ignorados; decimal con coma o punto (`10+2,5` → `[10.0, 2.5]`).
- Cada valor debe ser `> 0` y `< 100`.
- Cualquier otro formato → `ValueError` con mensaje en castellano.
- Los constraints de los modelos convierten `ValueError` en `ValidationError`.
- Porcentajes (pronto pago, flete, percepción, internos): `0 ≤ x < 100`, constraint.

## Integración

### Orden de compra (`purchase.order.line`)

Nuevo campo `discount_cascade` (Char, almacenado, `readonly=True`, columna opcional).

Regla aplicada en los **tres caminos** de alta de línea:

1. `_compute_price_unit_and_date_planned_and_name` (alta manual / cambio de cantidad).
2. `purchase.order._update_order_line_info` (catálogo).
3. `_prepare_purchase_order_line` (reabastecimiento / reglas de reorden / MTO).

Regla:

- Si el comprador pisó el precio (`technical_price_unit != price_unit`) → no tocar.
- Buscar el supplierinfo del proveedor de la orden con
  `product_tmpl_id.with_company(company)._get_reference_cost_seller(partner=partner)`.
- Si ese supplierinfo tiene `effective_discount_cascade` no vacía →
  `discount = discount_equivalent_pct` y `discount_cascade = effective_discount_cascade`.
- Si no → comportamiento core (`discount = selected_seller_id.discount`),
  `discount_cascade = False`.

Pronto pago, flete, percepción e internos **no** van a la OC.

### Listas de precios (`product.pricelist.item`)

- `base` agrega `('replacement_cost', 'Costo de Reposición')`,
  `ondelete={'replacement_cost': 'set default'}`.
- `_compute_base_price`: si `base == 'replacement_cost'` usa
  `product.replacement_cost`; si da 0 → fallback a `standard_price` con warning (igual
  que la base `reference_cost`). Conversión de UoM y moneda vía el helper del base.

### Refactor en `alpardata_purchase_reference_cost` (sin cambio de comportamiento)

1. `product.pricelist.item._convert_commercial_cost(product, cost, uom, date, currency)`:
   extrae la conversión UoM + moneda que hoy está inline en `_compute_base_price`.
2. `product.template._get_divergence_base_cost()`: devuelve `self.reference_cost`;
   `_compute_cost_divergence` lo usa en lugar de leer `reference_cost` directo.
3. Versión `19.0.2.2.0`. Los tests existentes deben pasar **sin modificaciones**.

### Semáforo de divergencia

El AVCO sale de facturas ya bonificadas. El módulo nuevo sobreescribe
`_get_divergence_base_cost()` para devolver `net_purchase_cost` (neto bonificado, sin
adicionales), evitando alertas falsas en proveedores con bonificaciones.

## Interfaz

- **Proveedor** (`res.partner`, pestaña Compra): grupo "Condiciones comerciales".
- **Supplierinfo** (form y list): `use_own_conditions`; campos `own_*` visibles con el
  tilde, `effective_*` de solo lectura sin él; columnas opcionales
  `effective_discount_cascade`, `discount_equivalent_pct`, `replacement_cost`;
  `replacement_cost_breakdown` en el form.
- **Producto**: `replacement_cost` junto a `reference_cost`; `internal_tax_pct` en la
  pestaña Compra; columna opcional `replacement_cost` en la lista.
- **Categoría**: `internal_tax_pct`.
- **OC**: columna opcional `discount_cascade`.

Convenciones Odoo 19 a respetar: `<chatter/>`, `<search>` sin `<group string>`,
`group_ids` (no `groups_id`), `invisible="..."` en vez de `attrs`.

## Seguridad

- Campos de condiciones en proveedor, `use_own_conditions`/`own_*` en supplierinfo e
  `internal_tax_pct` (producto y categoría): lectura para cualquier usuario interno,
  edición solo para `purchase.group_purchase_manager`.
- Implementación:
  - Vistas: campo computado no almacenado `can_edit_commercial_conditions`
    (`self.env.user.has_group('purchase.group_purchase_manager')`) en `res.partner`,
    `product.supplierinfo`, `product.template` y `product.category`;
    `readonly="not can_edit_commercial_conditions"` en los campos protegidos.
  - Servidor: `write`/`create` de esos modelos llaman a
    `_check_commercial_conditions_access(vals)`, que levanta `AccessError` si `vals`
    toca un campo protegido y el usuario no es manager (se saltea con `sudo()` /
    `self.env.su`).
- No hay modelos nuevos → no hay ACL nuevas.

## Textos e i18n

Strings en castellano, igual que el módulo base. No se genera `i18n/`.

## Tests (`alpardata_purchase_replacement_cost/tests/`)

1. `test_discount_cascade.py` — parseo: `10+5+3` → 17,065; `10+2,5`; espacios; vacío;
   `abc`, `10++5`, `100`, `0`, `-5` → error.
2. `test_conditions.py` — herencia proveedor → supplierinfo; `use_own_conditions`;
   valores distintos por empresa (`company_dependent`); constraints de porcentajes.
3. `test_replacement_cost.py` — ejemplo canónico = 854,2305; UoM (pack x24); moneda
   (USD); internos desde categoría y pisado a mano; sin lista → 0;
   `_get_replacement_cost_for` con UoM/moneda y fallback.
4. `test_pricelist.py` — base `replacement_cost`; fallback a `standard_price`.
5. `test_purchase_order.py` — descuento y `discount_cascade` en alta manual, catálogo y
   reabastecimiento; precio manual respetado; sin cascada → `supplierinfo.discount`.
6. `test_divergence.py` — AVCO = neto bonificado → `ok`.

Tests del base: pasan sin cambios.

## Fuera de alcance

- Importador de listas de proveedores → punto 2.
- Cola de etiquetas / margen erosionado → punto 3.
- Cotización de reposición para USD → punto 4.
- Margen de reposición en ventas / POS → punto 5.
- Precio de reposición en OC por reabastecimiento **en el módulo base** (hoy no aplica
  `reference_cost` en `_prepare_purchase_order_line`): deuda anotada, no se toca acá.
- Recargos (bonificaciones negativas).
