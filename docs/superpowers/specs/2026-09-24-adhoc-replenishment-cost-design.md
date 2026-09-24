# Costo de reposición sobre Adhoc y migración de Broda

**Fecha:** 2026-09-24
**Módulos nuevos:**
- `alpardata_replenishment_cost` — extensión de `product_replenishment_cost` de Adhoc.
- `alpardata_reference_cost_migration` — migración de un solo uso para Grupo Broda.

**Depende de:** `AlparLabs/product` (fork de `ingadhoc/product`, rama `19.0`):
`product_replenishment_cost`, `product_replenishment_cost_stock`,
`product_replenishment_cost_sale_margin`, `product_planned_price`.
**Rama objetivo:** `19.0`
**Reemplaza a:** punto 1 del roadmap (`2026-09-24-replacement-cost-design.md`) y al módulo
`alpardata_purchase_reference_cost`.

## Contexto y decisión

El costo comercial para retail (Broda, y FRAT a continuación) se construye **sobre el
módulo de Adhoc** `product_replenishment_cost`, extendiendo sólo lo que falta. Motivo:
menos mantenimiento propio; Adhoc lo mantiene y lo porta en cada versión.

Hoy Broda tiene en producción `alpardata_purchase_reference_cost` (19.0.2.1.3). Datos
relevados en producción (2026-09-24, sólo lectura):

| Dato | Valor |
|---|---|
| Fichas de proveedor con `reference_cost > 0` | ~7.845 (FRAT by BRODA 5.073, globales 2.135, BRODA SA 636, SUPRA 1) |
| De esas, con vigencia por fecha | 2.712 (BRODA SA 626, globales 2.086) |
| Fichas con `price > 0` | 131 (el campo `price` no se mantiene) |
| Historial `product.supplierinfo.cost.history` | ~12.180 registros |
| Programaciones `product.cost.schedule` | 0 |
| Reglas de lista con base `reference_cost` | 0 (11.799 sobre `list_price`, 8 sobre otra lista) |
| Empresas | BRODA SA es matriz de 9 (FRAT, Bosco, Coraje, NIPOTI, hospitales…); FRAT by BRODA independiente |

Se usan las listas con vigencia y la jerarquía matriz → sucursal. No se usan
programaciones ni listas de precios basadas en costo.

## Qué da Adhoc y qué falta

Adhoc da: costo de reposición por producto (desde el proveedor principal, el último
precio o manual, en cualquier moneda), reglas reutilizables de recargos y descuentos
(líneas en secuencia con % sobre el acumulado, monto fijo o expresión), precio neto por
ficha de proveedor, precio sugerido en la OC y en el reabastecimiento, margen de ventas
con costo de reposición y precio planificado (reposición × (1 + margen) + recargo, con
asistente y cron para pasarlo a `list_price`).

Falta, y lo cubre `alpardata_replenishment_cost`:

1. Respetar las **fechas de vigencia** de las fichas al calcular el costo del producto.
2. **Jerarquía de empresas** (sucursal → matriz → global), también en la OC.
3. **Unidad de medida** de la ficha al calcular el costo del producto.
4. **Regla de costo por proveedor**, heredada por sus fichas.
5. **Margen por categoría**, heredado por los productos.
6. **Historial** de cambios de precio y regla en las fichas.
7. **Cierre automático de vigencias** al cargar una ficha con fecha.

Se abandonan: programación de costos, semáforo de divergencia AVCO, base de lista
"Costo de Referencia/Reposición", y todo `alpardata_purchase_replacement_cost`.

## `alpardata_replenishment_cost`

### 1. Proveedor vigente

**`product.supplierinfo._get_filtered_supplier(company_id, product_id, params)`** (core):

- Acepta fichas de `company_id`, de sus matrices (recorriendo `parent_id`) y globales
  (sin empresa); mantiene el resto de las condiciones del core (proveedor activo,
  variante).
- Para un mismo proveedor (`partner_id`), conserva sólo las fichas del nivel de empresa
  más específico: si la sucursal tiene ficha propia de ese proveedor, se descartan las de
  la matriz y las globales de ese proveedor.
- Todo lo que usa `_select_seller` / `_get_filtered_sellers` (OC manual, catálogo,
  reabastecimiento, precio neto de Adhoc en la OC) queda cubierto.

**`product.template._compute_supplier_data`** (Adhoc), override completo:

- Candidatas: `seller_ids._get_filtered_supplier(self.env.company, False)` con
  `date_start <= hoy <= date_end` (fechas vacías = sin límite) y `net_price > 0`.
- Orden según `replenishment_cost_type`:
  - `supplier_price`: empresa más específica primero (sucursal, matriz, global — igual
    que el módulo actual, para que la verificación de la migración dé 0 diferencias),
    luego `sequence` asc, luego `date_start` desc (sin fecha al final), luego `id` asc.
  - `last_supplier_price`: `last_date_price_updated` desc.
- `supplier_price` = `net_price` de la elegida **convertido de `product_uom_id` de la
  ficha a `uom_id` del producto**; `supplier_currency_id` = moneda de la ficha.
- Mismas dependencias y `depends_context('company')` que Adhoc, más `seller_ids.date_start`,
  `seller_ids.date_end`, `seller_ids.product_uom_id`, `uom_id`.

### 2. Regla de costo por proveedor

- `res.partner.replenishment_cost_rule_id` (M2O `product.replenishment_cost.rule`),
  en la pestaña Compras.
- `product.supplierinfo.use_own_rule` (Boolean, "Regla propia").
- `product.supplierinfo.replenishment_cost_rule_id` (campo de Adhoc) se redefine como
  **computado almacenado editable** (`store=True, readonly=False, precompute=True`),
  `depends('partner_id.commercial_partner_id.replenishment_cost_rule_id', 'use_own_rule')`:
  sin regla propia toma la del proveedor comercial; con regla propia conserva el valor
  cargado.
- Editar la regla en la ficha desde la vista tilda `use_own_rule` (onchange); cambiar la
  regla del proveedor recalcula las fichas sin regla propia.

### 3. Margen por categoría

- `product.category.sale_margin` (Float, "Margen de venta (%)").
- `product.template.use_own_margin` (Boolean, "Margen propio").
- `product.template.sale_margin` (campo de Adhoc) se redefine como **computado almacenado
  editable**, `depends('categ_id.sale_margin', 'use_own_margin')`: sin margen propio toma
  el de la categoría.
- Pasar productos a `list_price_type = 'by_margin'` y activar el cron de precios
  planificados de Adhoc es **configuración comercial**, no lo hace el módulo ni la
  migración.

### 4. Historial

Modelo `product.supplierinfo.price.history` (sólo lectura desde la interfaz):

| Campo | Tipo |
|---|---|
| `supplierinfo_id` | M2O, `ondelete='set null'` |
| `product_tmpl_id`, `partner_id`, `company_id` | M2O |
| `old_price`, `new_price` | Float |
| `old_rule_id`, `new_rule_id` | M2O regla |
| `change_date` | Datetime |
| `changed_by` | M2O `res.users` |
| `change_reason` | Char (contexto `_change_reason`, default "Actualización manual") |

Se registra al crear una ficha (valor anterior = precio de la ficha vigente del mismo
proveedor, producto y empresa) y al cambiar `price` o `replenishment_cost_rule_id`.
Botón en la ficha de proveedor y en el producto; menú en Compras.

### 5. Cierre automático de vigencias

Al crear una ficha con `date_start`, las fichas del mismo proveedor, producto y empresa
vigentes a esa fecha reciben `date_end = date_start − 1 día`. No se tocan fichas que
empiezan después (futuras). Misma lógica que `_close_previous_records` del módulo actual.

### Seguridad

- Historial: lectura para usuarios de compras; escritura sólo por el sistema.
- Regla por proveedor y margen por categoría: editables por quien ya puede editar
  proveedores y categorías; la regla (`product.replenishment_cost.rule`) sigue con los
  permisos de Adhoc.

## `alpardata_reference_cost_migration`

Depende de `alpardata_replenishment_cost` y `alpardata_purchase_reference_cost` (se
instala con ambos presentes). El `post_init_hook` llama a funciones separadas (una por
paso) para poder testearlas:

1. **Control previo.** Si hay `product.pricelist.item` con `base` en
   (`reference_cost`, `replacement_cost`), aborta con `UserError` listando las reglas.
2. **Foto previa.** Para cada empresa con fichas (y cada sucursal de esas empresas), guarda
   `template.with_company(c).reference_cost` de los productos con fichas.
3. **Listas.** SQL: `price = reference_cost` donde `reference_cost > 0` (sin historial);
   `last_date_price_updated = write_date`.
4. **Historial.** SQL: copia `product_supplierinfo_cost_history` a
   `product_supplierinfo_price_history` (`old_reference_cost → old_price`,
   `new_reference_cost → new_price`, fecha, usuario, motivo, empresa, proveedor, producto,
   ficha).
5. **Productos.** `replenishment_cost_type = 'supplier_price'` en plantillas con alguna
   ficha con `price > 0`; el resto queda `manual`.
6. **Verificación.** Recalcula `replenishment_cost` con la misma foto de empresas y la
   compara con el paso 2 (tolerancia: precisión "Product Price"). Adjunta un CSV
   (`ir.attachment` en la empresa principal) con producto, empresa, costo anterior, costo
   nuevo y diferencia, y deja el resumen en el log. Esperado: 0 filas.

### Procedimiento

| Paso | Test (`grupobroda-test`) | Producción (`grupobroda`) |
|---|---|---|
| 0 | Restaurar test desde backup de producción (hoy test tiene `product_replenishment_cost` y el punto 1 instalados junto al módulo viejo) | Backup manual en Odoo.sh |
| 1 | Submódulo `AlparLabs/product` fijado a un commit; actualizar lista de aplicaciones | Igual |
| 2 | Instalar `alpardata_reference_cost_migration` | Igual |
| 3 | Revisar el CSV: 0 diferencias | Igual |
| 4 | Desinstalar `alpardata_purchase_replacement_cost` si está | No aplica |
| 5 | Desinstalar `alpardata_purchase_reference_cost` (arrastra al de migración) | Igual |
| 6 | Pruebas manuales: OC de sucursal con precio de matriz; costo del producto; ficha con fecha futura no cambia el costo de hoy; historial visible | Igual |

Desinstalar el módulo viejo borra `reference_cost` y las tablas de historial y
programación: se hace después del paso 3.

Después de producción: borrar del repo `alpardata_purchase_reference_cost`,
`alpardata_purchase_replacement_cost` y `alpardata_reference_cost_migration`, previa
confirmación de que ninguna otra instancia tiene instalado el módulo viejo (falfersa no
lo tiene; electricidadmaza, entredos y nuevosverdes no se pudieron verificar).

Aviso a usuarios: con Adhoc, el campo "Costo" del producto pasa a llamarse "Costo
contable" y aparece "Costo de reposición".

## Tests

`alpardata_replenishment_cost`:

1. Jerarquía: OC de sucursal toma la ficha de la matriz; ficha propia de la sucursal
   gana; empresa independiente no ve fichas de otra.
2. Vigencias: ficha futura y vencida no cuentan para el costo; a igual secuencia gana la
   de `date_start` más reciente.
3. UoM: ficha por pack x24 → costo por unidad.
4. Regla por proveedor: herencia, regla propia respetada, cambio en el proveedor
   propagado.
5. Margen por categoría: herencia, margen propio, precio planificado "por margen".
6. Historial: alta, cambio de precio y de regla, con motivo.
7. Cierre de vigencias: cierra la anterior, no toca las futuras.

`alpardata_reference_cost_migration` (datos creados con el módulo viejo instalado):

1. El control previo aborta con reglas de lista basadas en costo.
2. La copia de precio no genera historial.
3. El historial se copia completo.
4. Cambio de tipo de costo en productos con ficha.
5. La verificación sale vacía; con una diferencia forzada, aparece en el CSV.

## Impacto en el resto del roadmap

| Punto | Cambio |
|---|---|
| 1 | Reemplazado por este spec. |
| 2. Importador | Escribe `price` (no `reference_cost`); la vista previa calcula el neto con la regla de Adhoc; se quita la columna de bonificaciones por línea. |
| 3. Etiquetas y margen | `replenishment_cost` de Adhoc; recargo objetivo = `sale_margin` (con margen por categoría de este spec); "Aplicar precio sugerido" se reemplaza por el asistente de precio planificado de Adhoc. |
| 4. Cotización | Opcional; si se hace, se engancha a la conversión de Adhoc. |
| 5. Margen | Ventas: `product_replenishment_cost_sale_margin` de Adhoc (el margen del pedido pasa a ser de reposición). POS: módulo propio chico. |
| 6. Promociones | El precio de compra especial se aplica después del cálculo de Adhoc en la OC; se quitan referencias a `discount_cascade`. |

Specs y planes de los puntos 2, 3, 5 y 6 se actualizan en un paso aparte.

## Decisiones tomadas en el diseño

1. Construir sobre Adhoc en vez de mantener el stack propio.
2. Migración como módulo de un solo uso, no dentro de la extensión.
3. Regla de costo por proveedor con excepción por ficha.
4. Precio de venta por precio planificado de Adhoc (no base de lista en vivo).
5. Margen por categoría con excepción por producto; sin redondeo comercial por ahora.
6. Se porta el historial; se abandonan programación y semáforo AVCO.
