# Margen de reposición en ventas y punto de venta

**Fecha:** 2026-09-24
**Módulos nuevos:**
- `alpardata_sale_replacement_margin` — depende de `sale_margin`,
  `alpardata_purchase_replacement_cost`
- `alpardata_pos_replacement_margin` — depende de `point_of_sale`,
  `alpardata_purchase_replacement_cost`

**Rama objetivo:** `19.0`
**Roadmap:** punto 5 de 5 (ver `2026-09-24-commercial-cost-roadmap.md`)

## Problema

`sale_margin` y el POS calculan el margen con `standard_price` (AVCO). Con inflación,
vender a un precio que supera el AVCO no garantiza poder **reponer** la mercadería: el
margen contable da una falsa sensación de ganancia. El comercio necesita ver ambos:
margen contable (lo que dice el balance) y **margen de reposición** (lo que realmente
queda para volver a comprar).

## Objetivo

Guardar en cada línea de venta y de POS el costo de reposición unitario **al momento de
la venta** y calcular el margen de reposición, disponible en los análisis de ventas y de
POS junto al margen estándar.

Dos módulos separados para no obligar a instalar POS a quien solo usa ventas.

## Costo unitario de reposición

Se usa el helper del punto 1
`product.product._get_replacement_cost_for(company, uom, currency, date)`, que devuelve
`(costo, is_fallback)`: reposición convertida a `uom` y `currency`, o `standard_price`
convertido si la reposición es 0 (mismo fallback que las listas de precios).

## Ventas (`alpardata_sale_replacement_margin`)

### `sale.order.line`

| Campo | Tipo | Notas |
|---|---|---|
| `replacement_cost_unit` | Float | `store`, `precompute`, `readonly=True`, `copy=False`, `depends('product_id', 'company_id', 'currency_id', 'product_uom_id')` — mismo patrón que `purchase_price` pero no editable |
| `replacement_cost_fallback` | Boolean | `store`; True si se usó AVCO |
| `replacement_margin` | Float | `store`, `price_subtotal − replacement_cost_unit × product_uom_qty` |
| `replacement_margin_percent` | Float | `store`, `replacement_margin / price_subtotal` (0 si subtotal 0) |

`groups="base.group_user"` como los campos de `sale_margin`.

**Recalcular al confirmar**: en `sale.order.action_confirm`, antes de `super()`, se
recalcula `replacement_cost_unit` de todas las líneas con producto. Motivo: un
presupuesto puede quedar semanas abierto y con inflación el costo de la cotización ya
no es el de la venta. El campo no es editable, así que no hay ediciones manuales que
preservar.

### `sale.order`

- `replacement_margin` (Monetary, `store`, suma de líneas).
- `replacement_margin_percent` (Float, `store`).

### `sale.report`

- `replacement_margin` (Float) vía `_select_additional_fields`, dividido por
  `currency_rate` igual que `margin` en `sale_margin/report/sale_report.py`.

### Vistas

- Línea de pedido: columna opcional `replacement_cost_unit` y
  `replacement_margin_percent` (junto a `purchase_price`/`margin` de `sale_margin`).
- Pedido: `replacement_margin` junto a `margin` en el pie.
- Análisis de ventas: medida `replacement_margin`.

## POS (`alpardata_pos_replacement_margin`)

### `pos.order.line`

| Campo | Tipo | Notas |
|---|---|---|
| `replacement_cost_unit` | Float | `store`; se calcula en `create` (las líneas llegan sincronizadas desde el frontend) con la fecha de la orden |
| `replacement_margin` | Monetary | `store`, `price_subtotal − replacement_cost_unit × qty` (con devoluciones el `qty` negativo da margen negativo) |

La moneda de la línea es la de la orden (`order_id.currency_id`); se convierte desde la
moneda de la empresa con la fecha de la orden.

No se modifica el frontend del POS (JS): el cálculo es 100 % backend.

### `pos.order`

- `replacement_margin` (Monetary, computado almacenado, suma de líneas).

### `report.pos.order`

- `replacement_margin` en `_select`, siguiendo la expresión de `margin` en
  `point_of_sale/report/pos_order_report.py` (signo y `currency_rate`).

### Vistas

- Orden POS: `replacement_margin` junto al margen.
- Análisis de POS: medida `replacement_margin`.

## Migración de datos

No se recalculan pedidos/órdenes históricos al instalar: quedarían con el costo de
**hoy**, que es justamente el dato engañoso. Un `pre_init_hook` crea las columnas con
valor 0 antes de instalar, así el ORM no las recalcula para los históricos. (Documentarlo
en el README.)

## Tests

Ventas:
1. Línea nueva toma `replacement_cost_unit` del producto; margen y %.
2. UoM de la línea distinta (docena) y pedido en USD.
3. Sin costo de reposición → fallback AVCO + flag.
4. Cambio de costo entre presupuesto y confirmación → al confirmar se actualiza.
5. `sale.report` expone `replacement_margin`.

POS:
6. Orden creada vía `sync_from_ui` → líneas con costo y margen.
7. Devolución → margen negativo.
8. `report.pos.order` expone `replacement_margin`.

## Decisiones a validar (tomadas sin consultar)

1. **Dos módulos** (ventas y POS) en vez de uno.
2. El costo se **recalcula al confirmar** el pedido de venta y **no es editable**.
3. Fallback a **AVCO** cuando no hay costo de reposición.
4. **No** se recalculan datos históricos al instalar.
5. Sin cambios en el frontend del POS.
