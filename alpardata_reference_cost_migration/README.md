# AlparData - Migración Costo de Referencia → Adhoc

Módulo técnico de un solo uso para migrar los datos de `alpardata_purchase_reference_cost` al stack de costo de reposición de ADHOC (`product_replenishment_cost` + `alpardata_replenishment_cost`).

---

## Qué hace la migración (`post_init_hook`)

1. **Control previo:** Verifica que no existan reglas de listas de precios (`product.pricelist.item`) con base en `reference_cost` o `replacement_cost`. Si existen, aborta con `UserError` listando las reglas para que se ajusten manualmente.
2. **Foto previa:** Toma un snapshot del costo actual de los productos (`reference_cost`) por empresa.
3. **Migración de listas de proveedor:** Ejecuta un `UPDATE` en SQL copiando `price = reference_cost` y `last_date_price_updated = write_date` para todas las fichas con `reference_cost > 0` (sin generar entradas espurias de historial).
4. **Migración de historial:** Copia la tabla `product_supplierinfo_cost_history` a `product_supplierinfo_price_history` conservando precios anterior/nuevo, porcentaje de variación, fechas, usuarios, empresas y motivos de cambio.
5. **Tipo de costo:** Actualiza `replenishment_cost_type = 'supplier_price'` en todos los productos que tengan alguna ficha con precio cargado.
6. **Verificación y Reporte:** Recalcula `replenishment_cost` bajo el nuevo modelo y lo compara contra la foto previa. Genera un archivo CSV adjunto (`ir.attachment`) en la empresa principal (`migracion_costo_referencia_<fecha>.csv`) con las diferencias encontradas. Esperado: 0 filas.

---

## Runbook / Procedimiento de migración

> [!IMPORTANT]
> **Ejecutar la instalación desde la terminal de Odoo.sh**, NO desde la interfaz web, para evitar timeouts ante el volumen de fichas (~7.800 fichas y ~12.000 registros de historial):
> ```bash
> odoo-bin -i alpardata_reference_cost_migration --stop-after-init
> ```

### Pasos en Test (`grupobroda-test`) y Producción (`grupobroda`):

| Paso | Acción | Detalle |
|---|---|---|
| **0** | **Backup previo** | En test: restaurar desde producción. En producción: backup manual en Odoo.sh. |
| **1** | **Submódulos / Código** | Verificar que `AlparLabs/product` (ADHOC) y los nuevos módulos estén presentes en el build. |
| **2** | **Instalar migración** | Ejecutar por terminal: `odoo-bin -i alpardata_reference_cost_migration --stop-after-init`. |
| **3** | **Verificar reporte CSV** | Ir a **Ajustes → Técnico → Adjuntos**, descargar `migracion_costo_referencia_<fecha>.csv` y confirmar 0 diferencias. |
| **4** | **Desinstalar legado (test)** | En test: desinstalar `alpardata_purchase_replacement_cost` si existía. |
| **5** | **Desinstalar legado** | Desinstalar `alpardata_purchase_reference_cost` (esto arrastra y desinstala automáticamente `alpardata_reference_cost_migration`). |
| **6** | **Pruebas de humo** | Verificar: <br>1. OC de sucursal toma precio de la matriz.<br>2. Costo de reposición en plantilla de producto correcto.<br>3. Ficha con fecha futura no altera el costo de hoy.<br>4. Pestaña/botón de historial de precios accesible con registros previos. |

---

## Post-Migración

Una vez validada la migración en producción, este módulo junto con los módulos legados (`alpardata_purchase_reference_cost` y `alpardata_purchase_replacement_cost`) pueden ser eliminados del repositorio.
