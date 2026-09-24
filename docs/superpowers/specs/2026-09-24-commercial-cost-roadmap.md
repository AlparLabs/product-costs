# Roadmap: costo comercial para retail en Argentina

**Fecha:** 2026-09-24
**Base:** `product_replenishment_cost` de Adhoc (`AlparLabs/product`, rama `19.0`),
extendido por `alpardata_replenishment_cost`. Reemplaza al módulo propio
`alpardata_purchase_reference_cost` (en producción en Grupo Broda hasta la migración).

## Puntos

| # | Tema | Módulo | Spec | Plan | Depende de |
|---|---|---|---|---|---|
| 1 | Costo de reposición sobre Adhoc + migración de Broda | `alpardata_replenishment_cost`, `alpardata_reference_cost_migration` | `2026-09-24-adhoc-replenishment-cost-design.md` | `plans/2026-09-24-adhoc-replenishment-cost.md` | Adhoc |
| 2 | Importador de listas de proveedores | `alpardata_supplier_pricelist_import` | `2026-09-24-supplier-pricelist-import-design.md` ⚠ | `plans/2026-09-24-supplier-pricelist-import.md` ⚠ | 1 |
| 3 | Margen erosionado y etiquetas pendientes | `alpardata_price_change_labels` | `2026-09-24-price-change-labels-design.md` ⚠ | `plans/2026-09-24-price-change-labels.md` ⚠ | 1, `product_label_3x8` |
| 4 | Cotización comercial (USD) — **opcional** | `alpardata_commercial_currency_rate` | `2026-09-24-commercial-currency-rate-design.md` ⚠ | `plans/2026-09-24-commercial-currency-rate.md` ⚠ | 1 |
| 5 | Margen de reposición en POS (ventas: Adhoc) | `alpardata_pos_replacement_margin` | `2026-09-24-replacement-margin-design.md` ⚠ | `plans/2026-09-24-replacement-margin.md` ⚠ | 1 |
| 6 | Promociones de proveedor (sell-in / sell-out) | `alpardata_supplier_promotion` | `2026-09-24-supplier-promotion-design.md` ⚠ | `plans/2026-09-24-supplier-promotion.md` ⚠ | 3, `sale`, `point_of_sale` |

⚠ Escritos sobre el stack propio (`reference_cost` / `replacement_cost`). Hay que
actualizarlos a Adhoc antes de implementarlos; los cambios por punto están en la sección
"Impacto en el resto del roadmap" del spec del punto 1.

**Obsoletos** (se conservan como referencia): `2026-09-24-replacement-cost-design.md` y
`plans/2026-09-24-replacement-cost.md` — el punto 1 original, implementado como
`alpardata_purchase_replacement_cost` (mergeado en `19.0`, instalado sólo en
`grupobroda-test`; se desinstala en la migración).

## Orden de implementación

1 primero: prueba de concepto y migración en `grupobroda-test`, después en producción.
Después 2 → 3 → 6 → 5 (POS), cada uno actualizado a Adhoc antes de pasarlo a
implementar. 6 extiende el control de góndola del 3, así que va después.

**4 es opcional**: sólo hace falta si el cliente tiene proveedores que cotizan en dólares y
quiere fijar precios con un dólar distinto del contable.

Una rama y un PR por punto, contra `19.0`.

## Decisión: construir sobre `product_replenishment_cost` de Adhoc

**Fecha:** 2026-09-24. **Contexto:** Adhoc tiene en `AlparLabs/product` (rama `19.0`)
`product_replenishment_cost` y módulos relacionados (`_stock`, `_sale_margin`,
`product_planned_price`), que se superponen con `alpardata_purchase_reference_cost` y con
el punto 1 original. Se evaluó antes de entrar en retail con FRAT.

**Decisión:** colgarse de Adhoc y extender sólo lo que falta. Reemplaza una decisión
anterior del mismo día ("seguir con el stack propio"), que comparaba funcionalidades en
vez del costo de extender.

**Motivos:**

- Menos mantenimiento propio: Adhoc lo mantiene activamente y lo porta en cada versión.
- Lo que le falta (vigencias por fecha, jerarquía de empresas, unidad de medida, regla por
  proveedor, margen por categoría, historial) se cubre con una extensión chica.
- Migrar Broda es barato: en producción sólo usa las listas de proveedores; no usa
  programaciones ni listas de precios basadas en el costo de referencia.

**Reglas operativas:**

- No instalar `product_replenishment_cost` junto con `alpardata_purchase_reference_cost`
  fuera de la migración: los dos pisan el precio de la línea de compra.
- Fijar el submódulo `AlparLabs/product` a un commit en cada cliente.
- Antes de diseñar algo de costos o precios, revisar primero los repos de Adhoc.

## Flujo de trabajo

1. Se implementa cada plan en Antigravity.
2. Se revisa y corrige en Claude Code (`/code-review` sobre la rama).
3. Se valida en una instancia (no hay instancia ejecutable local: tests en Odoo.sh o la
   instancia de desarrollo que corresponda).
