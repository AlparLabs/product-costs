# AlparLabs Product Costs Suite

Suite de módulos de Odoo 19.0 para gestión de costos comerciales y de reposición en retail y distribución para Argentina.
Construido como extensión del stack de **`product_replenishment_cost`** de ADHOC (`AlparLabs/product`).

## Módulos de la suite

1. **`alpardata_replenishment_cost`**: Extiende `product_replenishment_cost` de ADHOC con:
   - Jerarquía de empresas sucursal → matriz en las fichas de proveedor.
   - Vigencias por fecha (`date_start`, `date_end`), UoM del proveedor y desempate por fecha más reciente.
   - Regla de costo por proveedor con excepción por ficha.
   - Margen por categoría de producto con excepción por plantilla.
   - Historial de cambios de precio de proveedor.
   - Cierre automático de vigencias anteriores.
2. **`alpardata_reference_cost_migration`**: Módulo de un solo uso para migrar datos históricos desde `alpardata_purchase_reference_cost` a los campos de ADHOC con informe de verificación CSV.
3. **`alpardata_supplier_pricelist_import`**: Importador masivo de listas de proveedores (Excel/CSV o %) con vista previa y vigencias, integrado a las reglas de ADHOC.
4. **`alpardata_price_change_labels`**: Alertas de margen erosionado y cola de etiquetas físicas de góndola pendientes de reimpresión (formato 3x8).
5. **`alpardata_pos_replacement_margin`**: Margen de reposición en Punto de Venta (TPV).
6. **`alpardata_supplier_promotion`**: Promociones de proveedor (sell-in y sell-out).

## Requisitos y dependencias
- Odoo 19.0
- Repositorio `AlparLabs/product` (rama `19.0`) en el addons-path.
