# Margen erosionado y cola de etiquetas pendientes

**Fecha:** 2026-09-24
**Módulo nuevo:** `alpardata_price_change_labels`
**Depende de:** `alpardata_purchase_replacement_cost` (punto 1), `product_label_3x8`
**Rama objetivo:** `19.0`
**Roadmap:** punto 3 de 5 (ver `2026-09-24-commercial-cost-roadmap.md`)

## Problema

Con inflación, lo que importa es cuánto tarda un aumento de costo en llegar a la góndola:

1. Si el precio de venta es fijo (`list_price` o regla de precio fijo), un aumento de
   costo **erosiona el margen** sin que nadie se entere.
2. Si el precio se calcula desde el costo (regla de lista con base reposición), el
   precio cambia solo, pero **la etiqueta de la góndola queda vieja**. En Argentina el
   precio exhibido es obligatorio (Res. 4/2025, Ley 27.743, ya contemplados en
   `product_label_3x8`).

## Objetivo

- Detectar productos cuyo margen sobre reposición quedó por debajo del objetivo.
- Mantener una **cola de etiquetas pendientes**: productos cuyo precio de góndola actual
  difiere del último impreso, sin importar la causa (costo, cotización, regla de lista,
  cambio manual).

## Definiciones

- **Lista de góndola**: `res.company.shelf_pricelist_id` (Ajustes → Compras, bloque
  "Costo de Referencia Comercial"). Si está vacía, se usa `list_price`.
- **Precio de góndola** (`shelf_price`): el `price_final` que calcula
  `report.product_label_3x8.report_producttemplatelabel3x8._get_label_info(product,
  pricelist)` sin promoción. Es **la misma función que imprime la etiqueta**: lo que se
  controla es exactamente lo que se imprime.
- **Precio de góndola sin impuestos** (`shelf_price_untaxed`): el `price_net` de esa
  misma función.
- **Recargo actual** (`markup_pct`):
  `(shelf_price_untaxed / replacement_cost − 1) × 100`. Si `replacement_cost = 0` → sin
  cálculo. Se usa recargo sobre costo (no margen sobre precio) porque es como se habla en
  el comercio argentino ("le pongo 40 arriba").
- **Recargo objetivo** (`target_markup_pct`): en la categoría; en el producto como
  computado almacenado editable, tomado de la categoría (mismo patrón que
  `internal_tax_pct` del punto 1).

## Modelo de datos

### `res.company`
- `shelf_pricelist_id` (M2O `product.pricelist`).
- `markup_tolerance_pct` (Float, default 2): tolerancia antes de alertar.

### `product.category`
- `target_markup_pct` (Float).

### `product.template`
- `target_markup_pct` (Float, computado almacenado editable desde `categ_id`).

### `product.price.watch` (nuevo)

Una fila por (producto, empresa), restricción única. La escribe el proceso de refresco
(no son computes de ORM: el precio depende de la fecha y de datos no almacenados).

| Campo | Tipo | Notas |
|---|---|---|
| `product_tmpl_id` | M2O, `ondelete='cascade'` | requerido |
| `company_id` | M2O | requerido |
| `shelf_price` | Float | precio de góndola al último refresco |
| `shelf_price_untaxed` | Float | |
| `replacement_cost` | Float | al último refresco |
| `markup_pct` | Float, computado almacenado | |
| `target_markup_pct` | related `product_tmpl_id.target_markup_pct` | |
| `markup_alert` | Selection `ok`/`below`/`no_cost`, computado almacenado | `below` si `markup_pct < target − tolerancia` |
| `label_printed_price` | Float | precio de la última etiqueta 3x8 regular impresa |
| `label_printed_date` | Datetime | |
| `label_variation_pct` | Float, computado almacenado | `shelf_price / label_printed_price − 1` |
| `label_pending` | Boolean, computado almacenado | `float_compare(shelf_price, label_printed_price, 2) != 0` |
| `refreshed_at` | Datetime | |

## Refresco

`product.price.watch._refresh(templates, company)`: calcula precio de góndola, sin
impuestos y reposición, y crea o actualiza las filas. Se ejecuta:

- **Cron diario** `_cron_refresh`: por empresa, sobre productos `sale_ok` activos de esa
  empresa o sin empresa, en lotes de 1000 con `commit` entre lotes (fuera de tests).
- **Botón "Actualizar"** en las listas (sobre las filas seleccionadas).

## Impresión

- Override de `product.label.layout.process()`: con `print_format == '3x8xprice'`,
  refresca las filas de los productos impresos y escribe `label_printed_price` = precio
  calculado con **la lista elegida en el wizard** (o `list_price` si no eligió) y
  `label_printed_date = now`. Si la lista del wizard difiere de la de góndola, el precio
  impreso no coincide con el controlado y el producto **sigue pendiente**.
- Las etiquetas de promoción (`3x8xpromo`) **no** tocan la cola.
- **Advertencia** en el wizard si la lista elegida difiere de la lista de góndola de la
  empresa (el precio impreso no coincidiría con el controlado).

## Instalación

`post_init_hook`: para cada empresa, corre el refresco y setea
`label_printed_price = shelf_price` para que al instalar **no** queden todos los
productos pendientes.

## Interfaz

- Menú **Inventario → Productos → Etiquetas pendientes**: lista de `product.price.watch`
  con `label_pending`, columnas precio impreso, precio actual, variación %, fecha de
  impresión; botones "Imprimir etiquetas" (abre `product.label.layout` con
  `print_format='3x8xprice'`, la lista de góndola y los productos seleccionados) y
  "Actualizar".
- Menú **Compras → Costos de Referencia → Margen erosionado**: filas con
  `markup_alert = 'below'`, columnas reposición, precio sin impuestos, recargo actual,
  recargo objetivo.
- Wizard de etiquetas: aviso si la lista elegida difiere de la de góndola.
- Ajustes: lista de góndola y tolerancia.

## Aplicar precio sugerido (productos con precio fijo)

Para productos cuyo precio sale del **precio de venta del producto** (sin regla en la
lista), un aumento de costo no mueve el precio: sólo aparece la alerta de margen. Desde la
vista **Margen erosionado**, el botón **"Aplicar precio sugerido"** (gerentes de compras)
calcula, para las filas seleccionadas:

```
sin_impuestos = reposición × (1 + recargo_objetivo / 100)
precio        = sin_impuestos × (1 + IVA incluido en precio)      # sólo impuestos "incluidos"
precio        = redondeo hacia arriba al múltiplo de `suggested_price_rounding`
                + `suggested_price_surcharge`                       # p. ej. 10 y −1 → termina en 9
```

y lo escribe en `product.template.list_price`; después refresca las filas (quedan en la
cola de etiquetas). Si el precio de góndola no cambió porque el producto tiene una regla
en la lista de góndola, avisa cuántos productos no se movieron.

`res.company` suma `suggested_price_rounding` (Float, 0 = sin redondeo) y
`suggested_price_surcharge` (Float), en Ajustes junto a la lista de góndola.

`list_price` no depende de la empresa: en multi-empresa el precio sugerido de una empresa
pisa el de todas. Se documenta en el README.

## Redondeo comercial (sin código)

El core ya lo cubre en las reglas de lista (`price_round`, `price_surcharge`,
`price_min_margin`, `price_max_margin`). Ejemplos a documentar en el README:
- Terminar en 99: redondeo 100, recargo −1.
- Múltiplos de 50: redondeo 50.

## Seguridad

- Ver colas y alertas: usuarios de inventario/ventas/compras.
- Editar `target_markup_pct` (categoría y producto): gerentes de compras, con el mismo
  mixin `commercial.conditions.access.mixin` del punto 1. Lista de góndola y tolerancia:
  quien acceda a Ajustes.
- `product.price.watch`: lectura para usuarios internos; escritura sólo por el
  proceso de refresco/impresión (`sudo`). Record rule multi-company.

## Tests

1. Refresco: `shelf_price` con impuestos incluidos, con y sin lista de góndola.
2. Recargo actual y alerta `below`/`ok`/`no_cost` con tolerancia.
3. `target_markup_pct` desde categoría y pisado a mano.
4. Cola: cambio de costo con regla base reposición → pendiente después del refresco;
   imprimir 3x8 regular → no pendiente; imprimir promo → sigue pendiente.
5. `post_init_hook`: nada pendiente al instalar.
6. Multi-company: filas independientes por empresa.
7. Precio sugerido: cálculo con IVA incluido y redondeo; aplicado a `list_price`; aviso
   cuando una regla de lista impide el cambio.

## Decisiones a validar (tomadas sin consultar)

1. **Recargo sobre costo**, no margen sobre precio de venta.
2. Detección por **snapshot + refresco** (cron diario + botón), no en tiempo real: el
   precio depende de datos no almacenados y fechas de vigencia. Sin refresco automático
   al aplicar importaciones o programaciones (YAGNI: el botón y el cron alcanzan).
3. La cola se vacía al **imprimir**, no al confirmar que la etiqueta se colocó.
4. Solo etiquetas **3x8 regulares** alimentan la cola; otros formatos de Odoo no.
5. Snapshots en un **modelo propio** por (producto, empresa).
6. "Aplicar precio sugerido" escribe `list_price` directo (sin vista previa): el usuario
   elige las filas en la lista antes de aplicar.
