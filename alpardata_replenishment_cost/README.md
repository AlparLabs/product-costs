# AlparData - Costo de Reposición (Extensión ADHOC)

Extensión de AlparData sobre el stack de costo de reposición y precio planificado de ADHOC SA (`product_replenishment_cost`, `product_replenishment_cost_stock`, `product_replenishment_cost_sale_margin`, `product_planned_price`).

---

## Mejoras sobre el stack de ADHOC

1. **Jerarquía multi-empresa (Sucursal → Matriz → Global):**
   - En Odoo estándar y ADHOC, la sucursal sólo ve fichas con su empresa exacta o globales.
   - Con este módulo, una sucursal hereda las listas de precios de su empresa matriz (y matrices sucesivas) si no tiene una ficha propia cargada para ese proveedor. A igual proveedor, siempre prevalece la ficha de la empresa más específica.
   - Las órdenes de compra (PO) creadas en una sucursal toman automáticamente el precio de la ficha de la matriz si no hay ficha local.

2. **Vigencias por fecha y desempate por inicio más reciente:**
   - Para el cálculo del costo de reposición (`replenishment_cost`) sólo se consideran fichas vigentes hoy (`date_start <= hoy` y `date_end >= hoy`).
   - Fichas con fechas futuras o vencidas se ignoran en el costo actual.
   - En caso de empate en empresa y secuencia, gana la ficha con `date_start` más reciente.

3. **Conversión de Unidad de Medida (UoM):**
   - Si la ficha del proveedor está expresada en una unidad de empaque o compra distinta a la unidad de medida principal del producto (ej: Pack x24 o Caja), el costo de reposición se convierte automáticamente a la unidad del producto mediante el factor de la UoM.

4. **Regla de costo por proveedor (Bonificaciones en Cascada):**
   - Se agrega el campo `replenishment_cost_rule_id` en el contacto/proveedor (`res.partner`).
   - Las fichas de proveedor (`product.supplierinfo`) heredan automáticamente la regla del proveedor comercial (`partner_id.commercial_partner_id`).
   - Si una ficha requiere condiciones especiales, cuenta con el flag `use_own_rule` (Regla propia). Al editar la regla desde el formulario de la ficha, se marca automáticamente como propia para no ser pisada por cambios futuros en el proveedor.
   - *Nota:* La propagación de una nueva regla desde el proveedor a sus fichas no genera historial individual en las fichas (el cambio queda trazable en el contacto).

5. **Margen de venta por categoría:**
   - Se agrega el campo `sale_margin` (%) en la categoría de productos (`product.category`).
   - Los productos (`product.template`) heredan automáticamente este margen para su fórmula de precio planificado (`by_margin`).
   - Si un producto requiere un margen particular, cuenta con el flag `use_own_margin` (Margen propio), el cual se activa automáticamente al modificar el margen en la ficha del producto.

6. **Historial de precios de proveedor (`product.supplierinfo.price.history`):**
   - Registra auditoría automática ante cada creación o modificación de precio o regla en la ficha de proveedor.
   - Almacena: fecha, usuario, precio anterior, precio nuevo, % de variación, regla anterior/nueva, empresa y motivo de cambio (`_change_reason`).
   - Accesible mediante smart-button en la ficha de proveedor y en la plantilla del producto, y a través del menú **Compras → Productos → Historial de precios de proveedor**.

7. **Cierre automático de vigencias anteriores:**
   - Al cargar una nueva ficha con fecha de inicio (`date_start`), el sistema busca fichas anteriores del mismo producto, proveedor y empresa y les asigna automáticamente como `date_end` el día previo (`date_start - 1 día`).
   - Fichas futuras posteriores a `date_start` no son alteradas.

---

## Criterio de Selección de Ficha Principal

El cálculo de reposición selecciona la ficha óptima aplicando el siguiente ordenamiento:
1. **Rango de jerarquía de empresa** (0: empresa activa, 1: empresa matriz, 2: matriz abuela... N: global sin empresa).
2. **Secuencia** (`sequence asc`).
3. **Fecha de inicio más reciente** (`date_start desc`, sin fecha al final).
4. **ID más reciente** (`id desc`).

---

## Configuración Comercial y Precios

- La activación del cálculo de precio de venta por margen (`list_price_type = 'by_margin'`) y la ejecución del cron periódico de actualización de `list_price` provienen del módulo `product_planned_price` de ADHOC y es una decisión de configuración comercial por compañía.
- Al instalar este módulo junto con `product_replenishment_cost_sale_margin`, el margen calculado en pedidos de venta (`sale.order.line`) toma como base el costo de reposición en lugar del costo contable.

---

## Incompatibilidad y Requisitos

- **Submódulo ADHOC requerido:** Requiere que los módulos de `AlparLabs/product` (rama `19.0`) estén presentes en el path de addons.
- **Módulos legados:** **NO debe instalarse en conjunto con `alpardata_purchase_reference_cost` ni `alpardata_purchase_replacement_cost`**, salvo durante la ejecución de la migración con `alpardata_reference_cost_migration`.
- **Licencia:** AGPL-3 (en conformidad con las dependencias de ADHOC).
