# Diseño: `stock_forecasted_lots` — Lotes disponibles en el informe de pronóstico

**Fecha:** 2026-07-08
**Versión Odoo:** 19.0
**Estado:** Aprobado por Santiago Tojo

## Problema

Cuando un comercial cotiza un producto con seguimiento por lote (ej.: cable vendido
por metro, donde cada lote es una bobina), no tiene visibilidad de los lotes
disponibles ni de cuántos metros quedan en cada bobina. Eso impide ofrecer al
cliente los metros restantes para llevarse la bobina completa y evita que queden
bobinas con pocos metros muertos en depósito.

## Solución

Extender el **informe de pronóstico** de Odoo (el que se abre desde el ícono de
disponibilidad de la línea de venta → "Ver pronóstico", o desde la ficha del
producto) agregando un apartado **"Lotes disponibles"** debajo del detalle del
pronóstico. El informe ya muestra nativamente los ingresos pactados y las salidas
comprometidas, por lo que el apartado de lotes lo complementa sin duplicar datos.

## Alcance y decisiones

- **Solo visualización.** No hay acciones sobre los lotes (no modifica cantidades
  de la línea de venta).
- **Solo productos con `tracking = 'lot'`.** Los productos por número de serie
  quedan excluidos (listarían cientos de unidades de a 1).
- **Filtrado por el almacén activo del informe.** El informe ya tiene selector de
  almacén en la cabecera; cambiar el almacén actualiza el apartado. Cuando se abre
  desde una línea de venta, el contexto ya trae el almacén de la orden
  (`warehouse_id`).
- **Datos por lote:** nombre del lote, cantidad en stock, reservado y disponible,
  tomados de `stock.quant` (campos `quantity`, `reserved_quantity`,
  `available_quantity`) en ubicaciones internas del almacén. El alcance de
  ubicaciones usa `warehouse.view_location_id` (todo el árbol del almacén:
  WH/Stock, WH/Input, WH/Output, WH/Pack, control de calidad, etc.) filtrado a
  `usage = 'internal'`, en vez de limitarse solo a `warehouse.lot_stock_id`.
  Es una elección deliberada: así el disponible por lote coincide con el mismo
  criterio que usa el resto del informe nativo para calcular el disponible del
  producto a nivel de almacén.
- **Orden:** disponible ascendente — las bobinas con pocos metros aparecen
  primero, que son las que conviene liquidar.
- **Unidades:** cantidades expresadas en la unidad de medida del producto.
- **Sin pronóstico entrante por lote:** los lotes de recepciones futuras
  generalmente no se conocen hasta recibir la mercadería; los ingresos pactados ya
  se ven en el informe nativo a nivel documento.

## Arquitectura

Módulo nuevo `stock_forecasted_lots` en la raíz del repo, siguiendo las
convenciones de la suite (versión `19.0.1.0.0`, autor AlparData, LGPL-3).

Puntos de extensión verificados en el código fuente de Odoo 19:

1. **Python** — `report/stock_forecasted.py`: heredar
   `stock.forecasted_product_product` y extender `_get_report_data()` para
   agregar la clave `lots` al dict de datos. Lee los quants con
   `lot_id != False`, producto en los `product_ids` del informe (con tracking
   por lote) y ubicación hija de `warehouse.lot_stock_id` (almacén resuelto por
   `_get_warehouse()`, que lee `warehouse_id` del contexto). El modelo del
   informe por plantilla (`stock.forecasted_product_template`) hereda del de
   variante, por lo que el override cubre ambos.
2. **Plantilla OWL por XML** — `static/src/stock_forecasted/forecasted_details.xml`:
   extensión de `stock.ForecastedDetails` con `t-inherit-mode="extension"` y
   xpath para insertar la sección después de la tabla principal. Se renderiza
   solo si `docs.lots` tiene elementos. **No requiere JavaScript propio.**
   El archivo se registra en el bundle `web.assets_backend` desde el manifest.
3. **i18n** — `i18n/es_AR.po` con las traducciones (código fuente en inglés,
   como el resto de la suite).

Estructura del módulo:

```
stock_forecasted_lots/
├── __init__.py
├── __manifest__.py          # depends: ['sale_stock']; assets: web.assets_backend
├── report/
│   ├── __init__.py
│   └── stock_forecasted.py
├── static/src/stock_forecasted/
│   └── forecasted_details.xml
├── i18n/
│   └── es_AR.po
└── tests/
    ├── __init__.py
    └── test_forecasted_lots.py
```

## Formato de datos

`_get_report_data()` devuelve, además de las claves nativas:

```python
'lots': [
    {
        'id': lot.id,
        'display_name': 'BOBINA-0042',
        'product_display_name': 'Cable 2mm',   # útil si el informe es multi-variante
        'quantity': 100.0,
        'reserved_quantity': 62.5,
        'available_quantity': 37.5,
        'uom': 'm',
    },
    ...
]
```

Agregación: un renglón por lote (suma de sus quants en el almacén). Se excluyen
lotes con disponible y stock en cero.

## Seguridad y permisos

No crea modelos, campos almacenados ni reglas. No usa `sudo()`. Requiere lo mismo
que hoy para abrir el informe de pronóstico: permiso de lectura de inventario.

## Manejo de errores

- Producto sin tracking por lote → la clave `lots` queda vacía y la sección no se
  renderiza (el informe se ve igual que el nativo).
- Sin quants con lote en el almacén → ídem, sección oculta.
- Contexto sin `warehouse_id` → `_get_warehouse()` nativo resuelve el primer
  almacén activo, mismo comportamiento que el resto del informe.

## Pruebas

Tests Python (`tests/test_forecasted_lots.py`, tag estándar `post_install`):

1. Producto con tracking por lote y quants en dos lotes → `lots` trae ambos con
   cantidades, reservado y disponible correctos, ordenados por disponible
   ascendente.
2. Filtrado por almacén: quants en dos almacenes → solo aparecen los del almacén
   del contexto.
3. Producto sin tracking → `lots` vacío.
4. Lote con reserva parcial (mov. de salida confirmado) → `reserved_quantity` y
   `available_quantity` reflejan la reserva.

La sección visual (plantilla OWL) se verifica manualmente en la instancia.
