# Promociones de proveedor

**Fecha:** 2026-09-24
**Módulo nuevo:** `alpardata_supplier_promotion`
**Depende de:** `alpardata_price_change_labels` (punto 3, que trae el punto 1 y
`product_label_3x8`), `sale`, `point_of_sale`
**Rama objetivo:** `19.0`
**Roadmap:** punto 6 (ver `2026-09-24-commercial-cost-roadmap.md`)

## Problema

Los proveedores (Coca-Cola, Arcor, etc.) proponen promociones por tiempo limitado:
"del 1 al 7, vendé la Coca 2,25 L a $1.999". Según el proveedor y la promo, la financian
de dos formas, y a veces de las dos a la vez:

- **Sell-in:** durante la promo facturan la mercadería más barata.
- **Sell-out:** facturan el precio normal y después reintegran (nota de crédito) un monto
  por cada unidad vendida en promo.

Si esto se carga como un precio del proveedor, ensucia el costo de reposición (baja una
semana y vuelve), el precio de venta sale calculado y no el pedido, la etiqueta no se
imprime como promoción, y nadie cuenta las unidades vendidas para reclamar el reintegro.

**Una promoción no es un costo: es un evento con inicio y fin.** Se modela aparte y no toca
el costo de referencia ni el de reposición.

## Objetivo

Una promoción con proveedor, productos y fechas que:

1. Cobra el **precio promo** en la caja y en ventas durante esas fechas, y vuelve solo al
   precio regular al terminar. Funciona con productos con regla de lista y con precio fijo.
2. Toma el **precio de compra especial** en las órdenes de compra de ese proveedor dentro
   de las fechas (sell-in).
3. Manda los productos a la cola de etiquetas del punto 3 como **etiqueta de promoción**
   ("antes / ahora") al empezar, y como etiqueta regular al terminar.
4. Calcula el **monto a reclamar** al proveedor (sell-out): unidades vendidas en promo ×
   reintegro por unidad.

Fuera de alcance: la contabilidad del reintegro (nota de crédito, conciliación). Se
resuelve en Contabilidad como hoy; este módulo sólo calcula el monto.

## Modelo de datos

### `supplier.promotion` (con `mail.thread`)

| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char | secuencia `PROM/AAAA/NNNN` |
| `partner_id` | M2O `res.partner` | proveedor, requerido |
| `company_id` | M2O | requerido |
| `date_start`, `date_end` | Date | requeridos, `date_end >= date_start` |
| `datetime_start`, `datetime_end` | Datetime, computados almacenados | 00:00:00 y 23:59:59 de esas fechas en la zona horaria de la empresa (partner de la empresa; por defecto `America/Argentina/Buenos_Aires`), en UTC |
| `pricelist_ids` | M2M `product.pricelist` | listas donde rige el precio promo; default: la lista de góndola de la empresa (punto 3) |
| `sell_in` | Boolean | usa precio de compra especial |
| `sell_out` | Boolean | el proveedor reintegra por unidad vendida |
| `reimbursement_type` | Selection `fixed` / `difference` | sólo sell-out: monto fijo por unidad, o diferencia entre precio regular y promo |
| `state` | Selection `draft` / `confirmed` / `done` / `cancelled` | |
| `line_ids` | O2M | |
| `amount_to_claim`, `revenue` | Monetary, computados almacenados | suma de líneas |
| `note` | Text | |

### `supplier.promotion.line`

| Campo | Tipo | Notas |
|---|---|---|
| `promotion_id` | M2O, `ondelete='cascade'` | |
| `product_id` | M2O `product.product` | requerido; único por promoción |
| `promo_price` | Float | precio de venta promo, **mismo criterio de impuestos que el precio de venta del producto** |
| `regular_price` | Float | foto del precio regular al confirmar (lista de la promo sin reglas de promo) |
| `purchase_price` | Float | sell-in: precio de compra especial, **neto**, UoM del producto, moneda de la empresa |
| `reimbursement_amount` | Float | sell-out `fixed`: reintegro por unidad |
| `reimbursement_unit` | Float, computado almacenado | `fixed` → `reimbursement_amount`; `difference` → `regular_price − promo_price` |
| `qty_sold`, `revenue` | Float / Monetary | los escribe la liquidación |
| `amount_to_claim` | Monetary, computado almacenado | `qty_sold × reimbursement_unit` (0 si no es sell-out) |
| `pricelist_item_ids` | O2M `product.pricelist.item` | reglas creadas por la promo |

### `product.pricelist.item`

- `supplier_promotion_line_id` (M2O, `ondelete='cascade'`, index).

## Flujo

1. **Borrador:** se cargan proveedor, fechas, listas, tipo y líneas.
2. **Confirmar** (`action_confirm`), con validaciones:
   - al menos una línea; `promo_price > 0`;
   - sell-in → `purchase_price > 0` en todas las líneas;
   - sell-out `fixed` → `reimbursement_amount > 0`;
   - sin superposición con otra promo confirmada del mismo producto, lista y fechas;
   - hay al menos una lista.

   Por cada línea guarda `regular_price` (precio de la primera lista de la promo, sin
   reglas de promo, a la fecha de inicio). Por cada línea y lista crea una regla
   `product.pricelist.item`:
   - `applied_on='0_product_variant'`, `compute_price='fixed'`, `fixed_price=promo_price`;
   - `date_start=datetime_start`, `date_end=datetime_end`;
   - `supplier_promotion_line_id`.

   Por el orden de reglas de Odoo (`applied_on`, …, `id desc`), una regla por variante
   recién creada le gana a cualquier regla por plantilla, categoría o global, y al precio
   fijo del producto.
3. **Liquidar** (`action_compute_liquidation`, se puede correr en cualquier momento):
   recalcula `qty_sold` y `revenue` por línea.
   - POS: `pos.order.line` con orden en estado `paid`/`done`, `pricelist_id` de la orden en
     las listas de la promo, `date_order` dentro de las fechas. Las devoluciones restan.
   - Ventas: `sale.order.line` con pedido en estado `sale`, mismas condiciones, cantidad
     convertida a la UoM del producto.
4. **Cerrar** (`action_done`): liquida y pasa a `done`. Sólo después de `date_end`.
5. **Cancelar** (`action_cancel`, desde borrador o confirmada): borra las reglas; el
   precio vuelve al regular en el momento. **Volver a borrador** desde cancelada.

Editar fechas, listas o líneas sólo en borrador.

## Precio regular durante la promo

`product.pricelist._get_applicable_rules_domain` se extiende: con el contexto
`skip_supplier_promotions=True` excluye las reglas con `supplier_promotion_line_id`. Así se
obtiene el precio "antes" para la etiqueta y para `regular_price`.

## Compras (sell-in)

En las órdenes de compra del proveedor de la promo (`commercial_partner_id`), con
`date_order` dentro de las fechas y promo confirmada con `sell_in`:

- `price_unit` = `purchase_price` convertido a la UoM de la línea y a la moneda de la
  orden; `discount = 0`; `discount_cascade = False` (el precio especial ya es neto).
- Se aplica en los mismos tres caminos que la cascada del punto 1: alta manual (compute),
  catálogo (`_update_order_line_info`) y reabastecimiento (`_prepare_purchase_order_line`).
- Precio puesto a mano → no se toca.

El costo de referencia y el de reposición **no cambian**; el AVCO sí baja, porque la
compra fue más barata (es real).

## Etiquetas (integración con el punto 3)

`product.price.watch` suma:

- `promotion_line_id`: línea de promo confirmada y vigente hoy para el producto, la
  empresa y la lista de góndola (si la empresa no tiene lista de góndola, cualquier lista
  de la promo).
- `label_expected_kind` (computado): `promo` si hay promo vigente, si no `regular`.
- `label_printed_kind`: `regular` / `promo`, lo escribe la impresión.
- `label_pending` pasa a ser: precio distinto **o** tipo de etiqueta distinto.
- `markup_alert` suma el valor `promo` ("En promoción"): durante la promo no se alerta
  margen bajo.

Impresión (`product.label.layout.process`):

- `3x8xpromo` sobre productos con promo vigente → se registra el precio impreso y
  `label_printed_kind='promo'`.
- `3x8xprice` → `label_printed_kind='regular'` (el punto 3 ya registra el precio).

Contenido de la etiqueta: `_get_label_info` de `product_label_3x8` se extiende. Con
`is_promo` y sin Loyalty ni descuento manual, si el producto tiene promo vigente, llama a
la función original con la lista sin reglas de promo (precio regular) y
`promo_discount = (1 − promo/regular) × 100`. Resultado: "antes $regular, ahora $promo",
con el porcentaje. No se duplica la lógica de la etiqueta.

Al terminar la promo, el precio vuelve al regular y el tipo esperado pasa a `regular`: el
refresco del punto 3 la manda a la cola.

## Margen

Durante la promo el margen de reposición (punto 5) de esos productos baja: es real, y lo
compensa el reintegro. El módulo **no** modifica el punto 5. El total a reclamar y la
facturación de la promo se ven en la liquidación. Sumar el reintegro al margen de cada
línea queda para una segunda etapa, si hace falta.

## Interfaz

- Menú **Compras → Productos → Promociones de proveedor** (lista, formulario, búsqueda
  por proveedor, estado y vigencia; filtro "Vigentes").
- Formulario: cabecera con Confirmar / Liquidar / Cerrar / Cancelar / Volver a borrador;
  líneas editables en borrador; en la liquidación, columnas `qty_sold`, `revenue`,
  `reimbursement_unit`, `amount_to_claim` con totales.
- Lista de líneas de promociones (análisis): agrupable por proveedor y promo, exportable a
  Excel para mandar el reclamo.

## Seguridad

- Usuarios de compras: leer, crear y editar en borrador; confirmar.
- Gerentes de compras: además, borrar.
- Record rules multi-company en promociones y líneas.

## Tests

1. Confirmar crea reglas con fechas en cada lista; cancelar las borra.
2. Precio de lista: promo dentro de las fechas, regular fuera; con precio fijo del
   producto y con regla de reposición.
3. `skip_supplier_promotions` devuelve el precio regular; `regular_price` guardado.
4. Validaciones de confirmación (sin líneas, sell-in sin precio, superposición).
5. Sell-in: línea de OC dentro de las fechas toma el precio especial sin descuento; fuera
   de las fechas, lista + cascada; precio manual respetado; reabastecimiento.
6. Liquidación: ventas (pedido confirmado con la lista de la promo cuenta; con otra lista
   no); POS con venta y devolución.
7. Reintegro `fixed` y `difference`.
8. Etiquetas: durante la promo `markup_alert='promo'` y pendiente hasta imprimir la
   etiqueta de promo; `_get_label_info` devuelve antes/ahora; al terminar vuelve a quedar
   pendiente como regular.

## Decisiones a validar (tomadas sin consultar)

1. El precio promo va como **regla por variante con fechas** en las listas elegidas. Para
   productos con precio fijo, la caja tiene que usar una de esas listas (en Odoo toda caja
   tiene una).
2. ~~Las unidades para el reclamo son las vendidas con una lista de la promo~~ —
   **validada (2026-09-24):** sólo cuentan las ventas hechas con una lista de la promo,
   dentro de las fechas (POS y ventas). Ventas con otras listas (p. ej. mayoristas) no
   cuentan.
3. `difference` usa los precios tal como están cargados (con o sin IVA, según el producto).
4. El precio de compra especial es **neto**: pisa la cascada del punto 1.
5. No se modifica el margen del punto 5.
6. Fechas completas (día entero) en la zona horaria de la empresa; sin horarios.
