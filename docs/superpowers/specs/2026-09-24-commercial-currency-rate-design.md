# Cotización comercial para costos en moneda extranjera

**Fecha:** 2026-09-24
**Módulo nuevo:** `alpardata_commercial_currency_rate`
**Depende de:** `alpardata_purchase_reference_cost` (con el refactor del punto 1)
**Rama objetivo:** `19.0`
**Roadmap:** punto 4 de 5 (ver `2026-09-24-commercial-cost-roadmap.md`)

## Problema

Muchos proveedores cotizan en USD. Hoy `reference_cost` se convierte a pesos con la
cotización contable de Odoo (`res.currency.rate`, normalmente BNA/ARCA) a la fecha de
hoy. Pero para **fijar precios** el comercio suele usar otra cotización: el dólar al que
efectivamente repone (BNA vendedor del día de pago, MEP, o una cotización interna con
colchón). Cambiar la cotización contable para eso rompería la contabilidad.

## Objetivo

Una cotización **comercial**, separada de la contable, que se usa solo para convertir
costos comerciales (referencia y reposición) y las listas de precios basadas en ellos.
Las órdenes de compra y la contabilidad siguen con la cotización de Odoo.

## Modelo de datos

### `commercial.currency.rate` (con `mail.thread`)

| Campo | Tipo | Notas |
|---|---|---|
| `company_id` | M2O | requerido, default activa |
| `currency_id` | M2O `res.currency` | requerido, distinta de la moneda de la empresa |
| `date` | Date | requerido, default hoy |
| `rate` | Float | **pesos por 1 unidad de moneda extranjera** (forma humana: 1 USD = 1.450 ARS), `> 0`, `tracking=True` |
| `note` | Char | p. ej. "MEP cierre", "BNA vendedor + 2%" |

Restricción SQL única `(company_id, currency_id, date)`.
Orden `date desc`.

### `res.company`

- `commercial_rate_source` Selection `odoo` (default, comportamiento actual) / `manual`.
- `commercial_rate_max_age_days` Integer, default 7: si la última cotización manual es
  más vieja, se sigue usando pero se muestra un aviso en el tablero de cotizaciones.

## Conversión

### Hook en el módulo base (refactor sin cambio de comportamiento)

`product.template._convert_commercial_currency(amount, from_currency, to_currency, company, date)`:
default `from_currency._convert(amount, to_currency, company, date, round=False)`.

Se usa en:
- `product.template._compute_reference_cost` (supplierinfo → moneda de la empresa).
- `product.pricelist.item._convert_commercial_cost` (moneda de la empresa → moneda de la
  lista), creado en el punto 1.

**No** se usa en la orden de compra: la OC es un documento transaccional en su moneda y
sigue con la cotización contable.

Versión del base: la siguiente menor después del punto 1 (`19.0.2.3.0`).

### Override en el módulo nuevo

Si `company.commercial_rate_source == 'manual'`:
- `from == to` → `amount`.
- `from` extranjera, `to` = moneda empresa → `amount × rate(from)`.
- `from` = moneda empresa, `to` extranjera → `amount / rate(to)`.
- Ambas extranjeras → pasar por la moneda de la empresa.
- `rate(x)` = registro de `commercial.currency.rate` de la empresa y moneda con
  `date <= fecha` más reciente.
- Sin cotización manual para esa moneda → fallback al comportamiento default
  (cotización contable) y `_logger.warning`.

## Interfaz

- Menú **Compras → Configuración → Cotizaciones comerciales**: lista editable
  (fecha, moneda, cotización, nota), agrupable por moneda.
- Ajustes → Compras: fuente de cotización comercial y antigüedad máxima.
- En la ficha de producto, junto a `reference_cost`, un texto de ayuda cuando el
  proveedor vigente está en otra moneda: "Convertido a USD 1 = $1.450 (comercial,
  24/09/2026)". Campo computado no almacenado `reference_cost_rate_info` (Char).
- En la lista de cotizaciones, la más nueva de cada moneda se marca en rojo
  (`is_stale`) si es más vieja que `commercial_rate_max_age_days`.

## Relación con el punto 3

Como `reference_cost` y `replacement_cost` no se almacenan, una cotización nueva cambia
al instante los costos y los precios de reglas basadas en reposición. El refresco del
punto 3 (cron o botón) detecta los precios de góndola cambiados y los manda a la cola de
etiquetas. No hay acoplamiento directo entre módulos.

## Seguridad

- Leer cotizaciones: usuarios de compras.
- Crear/editar/borrar: `purchase.group_purchase_manager`.
- Record rule multi-company.

## Tests

1. Fuente `odoo`: mismo resultado que hoy (regresión).
2. Fuente `manual`: USD → ARS con la cotización vigente a la fecha; toma la más reciente
   `<= fecha`, no una futura.
3. ARS → USD (lista de precios en USD) divide.
4. Sin cotización manual para EUR → fallback contable.
5. Unicidad por empresa/moneda/fecha; `rate > 0`.
6. OC en USD sigue usando la cotización contable.
7. Multi-company: cada empresa su cotización.

## Decisiones a validar (tomadas sin consultar)

1. La cotización se carga **a mano** (no se consulta ninguna API: BNA/dolarapi quedan
   para una segunda etapa).
2. La cotización comercial **no afecta la OC**.
3. Unidad del campo: **pesos por dólar**, no la tasa inversa que usa Odoo internamente.
4. Una cotización por día por moneda y empresa.
