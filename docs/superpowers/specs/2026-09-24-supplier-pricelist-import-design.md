# Importador de listas de precios de proveedores

**Fecha:** 2026-09-24
**Módulo nuevo:** `alpardata_supplier_pricelist_import`
**Depende de:** `alpardata_purchase_replacement_cost` (punto 1)
**Rama objetivo:** `19.0`
**Roadmap:** punto 2 de 5 (ver `2026-09-24-commercial-cost-roadmap.md`)

## Problema

El costo de referencia solo sirve si está al día. Hoy se carga a mano, supplierinfo por
supplierinfo, o con `product.cost.schedule` producto por producto. En la práctica los
proveedores mandan:

- Un **Excel/CSV** con la lista completa (código, descripción, precio), con formato
  propio de cada proveedor.
- Un **aviso de aumento porcentual** ("+8% en toda la línea X desde el 1/10").

El wizard de actualización masiva (`product.reference.cost.mass.update`) se eliminó en
`56816c9` para alinear 19 con 18. Este módulo lo reemplaza con un flujo **auditable**
(queda registro de cada importación) y con **vista previa** antes de aplicar.

## Objetivo

Importar una lista de proveedor (archivo o porcentaje), ver el impacto (costo viejo,
nuevo, variación, reposición resultante) y aplicarla con fecha de vigencia, creando los
`product.supplierinfo` nuevos que el módulo base ya sabe manejar (cierre de vigencias,
historial).

## Modelo de datos

### `supplier.pricelist.import.profile` — perfil de mapeo por proveedor

| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char | requerido |
| `partner_id` | M2O `res.partner` | requerido |
| `company_id` | M2O `res.company` | default empresa activa |
| `file_type` | Selection `xlsx`/`csv` | |
| `sheet_name` | Char | vacío = primera hoja (xlsx) |
| `header_row` | Integer | fila de encabezados (1-based), default 1 |
| `csv_delimiter` | Char(1) | default `;` |
| `csv_decimal` | Selection `,`/`.` | default `,` |
| `csv_encoding` | Selection `utf-8`/`latin-1` | default `utf-8` |
| `match_by` | Selection `supplier_code`/`barcode`/`default_code` | default `supplier_code` |
| `col_code` | Char | nombre de columna del código |
| `col_price` | Char | nombre de columna del precio de lista |
| `col_cascade` | Char | opcional: columna con bonificaciones por línea |
| `price_includes_vat` | Boolean | la lista viene con IVA |
| `vat_pct` | Float | default 21; se usa si `price_includes_vat` |

Los encabezados se comparan normalizados (minúsculas, sin acentos, espacios colapsados).

### `supplier.pricelist.import` — una importación (persistente, con `mail.thread`)

| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char | secuencia `IMPL/AAAA/NNNN` |
| `partner_id` | M2O | requerido |
| `company_id` | M2O | requerido |
| `mode` | Selection `file`/`percent` | |
| `profile_id` | M2O profile | requerido si `file` |
| `file` / `file_name` | Binary / Char | requerido si `file` |
| `percent` | Float | requerido si `percent`; puede ser negativo (baja) |
| `filter_categ_ids` | M2M `product.category` | modo `percent`, incluye hijas |
| `filter_tag_ids` | M2M `product.tag` | modo `percent` |
| `effective_date` | Date | requerido, default hoy |
| `state` | Selection `draft`/`preview`/`done`/`cancelled` | |
| `line_ids` | O2M líneas | |
| `applied_date`, `applied_by` | Datetime, M2O | readonly |
| contadores | Integer computados | cambios, sin cambio, no encontrados, errores |

### `supplier.pricelist.import.line`

| Campo | Tipo |
|---|---|
| `import_id` | M2O, `ondelete='cascade'` |
| `row_number` | Integer (fila del archivo; 0 en modo porcentaje) |
| `code` | Char (código leído) |
| `supplierinfo_id` | M2O `product.supplierinfo` |
| `product_tmpl_id` | M2O |
| `old_list_price`, `new_list_price` | Float (UoM y moneda del supplierinfo) |
| `variation_pct` | Float |
| `old_cascade`, `new_cascade` | Char |
| `old_replacement_cost`, `new_replacement_cost` | Float |
| `status` | Selection `change`/`unchanged`/`not_found`/`error` |
| `message` | Char |
| `to_apply` | Boolean (default True si `change`) |

## Flujo

1. **Borrador**: el usuario elige proveedor, modo, perfil/archivo o porcentaje+filtros,
   fecha de vigencia.
2. **Generar vista previa** (`action_preview`): borra líneas previas y las regenera.
   - Modo archivo: lee con `openpyxl` (xlsx) o `csv` (stdlib). Por cada fila con código:
     busca el supplierinfo vigente del proveedor para el producto con
     `product_tmpl._get_reference_cost_seller(partner=partner)` bajo
     `with_company(import.company_id)`. El producto se encuentra por:
     - `supplier_code`: `product.supplierinfo.product_code` del proveedor;
     - `barcode` / `default_code`: en `product.product`.
     Precio: si `price_includes_vat`, se divide por `(1 + vat_pct/100)`.
   - Modo porcentaje: todos los supplierinfo vigentes del proveedor (mismo resolver) cuyos
     productos cumplan los filtros; `new = old × (1 + percent/100)`.
   - `new_replacement_cost` se calcula con la misma fórmula del punto 1 (función pública
     del módulo 1, sin duplicar lógica), con la cascada nueva si viene en el archivo.
   - Filas sin código se ignoran; código sin producto → `not_found`; precio no numérico
     o ≤ 0 → `error`; mismo precio y misma cascada → `unchanged`.
   - Estado → `preview`.
3. **Revisar**: lista de líneas con filtros por estado y variación; el usuario puede
   destildar `to_apply`.
4. **Aplicar** (`action_apply`): por cada línea `change` con `to_apply`:
   crea un `product.supplierinfo` copiando el vigente (`partner_id`, `product_tmpl_id`,
   `product_id`, `company_id`, `product_code`, `product_name`, `product_uom_id`,
   `currency_id`, `min_qty`, `sequence`, `delay`, `price`, `use_own_conditions` y
   `own_*`) con `reference_cost = new_list_price`, `date_start = effective_date` y, si
   hay cascada nueva, `use_own_conditions = True` + `own_discount_cascade`. Contexto
   `_change_reason = 'Importación <name>'`. El `create` del base cierra la vigencia
   anterior y registra el historial.
   Estado → `done`, `message_post` con el resumen.
5. **Cancelar**: desde `draft`/`preview`.

Fecha de vigencia futura: funciona igual (el base ya maneja supplierinfos con
`date_start` futuro sin romper el vigente). **No** se usa `product.cost.schedule`,
porque ese modelo aplica siempre al proveedor principal y la importación es de un
proveedor puntual.

## Errores y límites

- Archivo ilegible, hoja inexistente o columna requerida ausente → `UserError` en
  `action_preview` con el nombre de la columna/hoja.
- Un mismo código repetido en el archivo → la segunda aparición queda `error`
  ("Código duplicado en fila N").
- Importaciones grandes (10k+ filas): la preview se genera en una sola transacción; las
  líneas se crean en batch (`create` con lista). Sin colas.

## Interfaz

- Menú **Compras → Productos → Importar listas de proveedores** (importaciones) y
  **Compras → Configuración → Perfiles de listas de proveedores**.
- Botón "Importar lista" en la ficha del proveedor (smart button con contador).
- Form con header de estados y botones `Generar vista previa` / `Aplicar` / `Cancelar`.

## Seguridad

- `purchase.group_purchase_user`: leer y crear importaciones, generar preview.
- `purchase.group_purchase_manager`: aplicar (`action_apply` verifica el grupo), borrar,
  gestionar perfiles.
- Record rules multi-company en los tres modelos.

## Tests

1. Lectura xlsx y csv (coma decimal, latin-1), encabezados normalizados.
2. Match por código de proveedor, barcode y referencia interna.
3. Estados de línea: `change`, `unchanged`, `not_found`, `error`, duplicado.
4. Precio con IVA.
5. Modo porcentaje con filtro por categoría (incluye hijas) y etiqueta.
6. Aplicar: nuevo supplierinfo con `date_start`, vigencia anterior cerrada, historial
   con motivo, `to_apply = False` respetado, cascada del archivo → `own_*`.
7. Fecha futura: el vigente de hoy no cambia; al llegar la fecha cambia `reference_cost`.
8. Usuario no manager no puede aplicar.

Los archivos de prueba se generan en el test con `openpyxl` / `io.StringIO`, no se
versionan binarios.

## Decisiones a validar (tomadas sin consultar)

1. Columnas por **nombre de encabezado**, no por letra. Resiste que el proveedor
   reordene columnas, pero no que las renombre.
2. Productos no encontrados **no se crean**: solo se informan.
3. La importación es **persistente** (auditoría), no un wizard transitorio.
4. Aplicar requiere **manager de compras**.
5. Filtros del modo porcentaje: categoría y etiqueta (Odoo core no tiene "marca").
