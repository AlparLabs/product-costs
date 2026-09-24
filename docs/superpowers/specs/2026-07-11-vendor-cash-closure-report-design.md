# Reporte "Cierre de Caja por Vendedor" — Diseño

**Fecha:** 2026-07-11
**Cliente:** Electricidad Maza S.R.L.
**Repo/rama destino:** enhancement-suite / 19.0
**Módulo nuevo:** `sale_vendor_cash_closure`

## Objetivo

Replicar el reporte de "Cierre de Caja" del sistema anterior del cliente: un
listado diario, comprobante por comprobante, agrupado por vendedor, que
clasifica cada importe en columnas (Contado, Cuenta Corriente/ND, NC Contado,
cobranzas de CtaCte, comprobantes MiPyme/FCE, descuentos, lista de precios).
Sirve para el control del cierre de caja unificando los dos canales de venta:
la app de Ventas y el Punto de Venta. El cliente factura todas las ventas, por
lo que `account.move` es la fuente única para ambos canales.

## Alcance y generación

- **Wizard por fecha** (TransientModel): campos fecha (default hoy) y
  compañía. Dos acciones: *Descargar PDF* y *Descargar XLSX*.
- Menú de acceso: Punto de Venta → Reportes y Contabilidad → Reportes.
- No está ligado al cierre de sesión del PDV (eso ya lo cubre
  `pos_retail_cash_closure_reports` en el repo pos_enhancements con otro
  enfoque, por método de pago).

## Universo de filas

Para la fecha elegida, solo documentos publicados (`state = 'posted'`):

1. **Comprobantes de venta del día:** `account.move` con `move_type` en
   (`out_invoice`, `out_refund`) y `invoice_date` = fecha del reporte.
   Incluye facturas, ND (out_invoice con doc ND) y NC de ambos canales.
2. **Cobranzas del día:** `account.payment` de cliente, entrante, publicado,
   con `date` = fecha del reporte. Son las filas de la columna
   "Dev.CtaCte D/Ant" (recibos que cobran cuenta corriente de días
   anteriores). Los cobros del propio PDV no generan `account.payment`
   individuales, por lo que no duplican contra las facturas contado.

Quedan fuera: borradores, cancelados, facturas de proveedor, pagos salientes.

## Clasificación Contado vs Cuenta Corriente

**Criterio único para todos los canales:** el comprobante es de **Cuenta
Corriente** si el partner comercial (`commercial_partner_id`) tiene activo el
check de límite de crédito (`use_partner_credit_limit`). Si no, es
**Contado**. El método de pago del PDV (incluso el de tipo "Cuenta del
cliente" / pay_later) **no** participa en la clasificación.

## Vendedor (agrupador)

- Si la factura proviene de una `pos.order` que tiene el campo
  `counter_salesperson_id` (módulo `pos_centralized_payment`, repo
  pos_enhancements) con valor → ese empleado es el vendedor.
  - Chequeo blando: `'counter_salesperson_id' in order._fields`. El módulo
    NO depende de `pos_centralized_payment` en el manifest.
- En cualquier otro caso → el comercial de la factura (`invoice_user_id`).
- Para los recibos de cobro → el comercial del pago o, en su defecto, el
  comercial del partner.
- Comprobantes sin vendedor resoluble → grupo "Sin vendedor" al final.

## Mapeo de columnas

Montos con IVA incluido (`amount_total`), expresados en moneda de la
compañía (conversión al tipo de cambio del comprobante si hiciera falta).
Cada comprobante aporta su monto a **una sola** columna de importes, según
su clasificación:

| Columna | Cálculo |
|---|---|
| Comprobante | Número l10n_ar del asiento (ej. `B001400431844`) o del recibo |
| Cliente | Nombre del partner (truncado en el PDF) |
| Contado | Facturas/ND de partners Contado (no FCE) |
| Cta.Cte/ND | Facturas/ND de partners CtaCte (no FCE) |
| N/C Cont. | NC de partners Contado (no FCE) |
| Dev.CtaCte D/Ant | Monto de los recibos de cobro del día |
| N/C Dev.CtaCte del día | NC del día de partners CtaCte (no FCE) |
| Fact. MiPyme | Facturas/ND con tipo de documento AFIP FCE: códigos 201, 206, 211 (facturas) y 202, 207, 212 (ND) |
| N/C MiPyme | NC FCE: códigos 203, 208, 213 |
| % Desc | Descuento promedio ponderado de las líneas del comprobante |
| Desct. | Monto total del descuento (bruto − con descuento, IVA incl. aproximado por proporción) |
| Cantid. CC | 1.00 si el comprobante es de CtaCte; el subtotal las suma (cuenta de comprobantes CC) |
| Lista | Lista de precios del `sale.order` / `pos.order` de origen (vacío si no hay origen) |

Notas:
- La clasificación FCE tiene prioridad: un comprobante FCE va a las columnas
  MiPyme aunque el partner sea Contado o CtaCte.
- En la fila de totales, `% Desc` no se suma (se deja el total de `Desct.`
  como referencia monetaria); el original sumaba porcentajes, lo cual no es
  significativo.

## Estructura del módulo

```
sale_vendor_cash_closure/
├── __init__.py
├── __manifest__.py          # depends: account, sale, point_of_sale,
│                            #          l10n_latam_invoice_document
├── security/ir.model.access.csv
├── wizard/
│   ├── __init__.py
│   ├── cash_closure_report_wizard.py
│   └── cash_closure_report_wizard_views.xml
├── report/
│   ├── __init__.py
│   ├── report_cash_closure_vendor.py    # AbstractModel: arma los datos
│   └── report_cash_closure_vendor.xml   # ir.actions.report + paperformat
├── views/
│   └── report_cash_closure_vendor_template.xml  # QWeb PDF
└── i18n/
    ├── es.po
    └── es_AR.po
```

- **La lógica de datos vive en un solo lugar** (AbstractModel del reporte):
  devuelve `{groups: [{salesperson, rows: [...], subtotals: {...}}],
  grand_totals: {...}}`. El QWeb (PDF) y el generador XLSX consumen la misma
  estructura.
- **XLSX** con el patrón de `account_invoice_line_export`: xlsxwriter en
  memoria → `ir.attachment` → `ir.actions.act_url` de descarga. Sin
  dependencias nuevas.
- **PDF** QWeb con paperformat A4 apaisado, fuente condensada; fiel al
  original: encabezado "Cierre de Caja: <fecha>", grupos `Vendedor:
  NOMBRE`, subtotal por vendedor, total general al pie.
- Strings del módulo en inglés, traducciones en `es.po` / `es_AR.po`.

## Orden y presentación

- Vendedores en orden alfabético; "Sin vendedor" al final.
- Dentro de cada grupo, comprobantes por número.
- Subtotal por vendedor (todas las columnas de importe + Cantid. CC).
- Total general: fila de subtotales global al pie.

## Manejo de errores

- Sin datos para la fecha → `UserError` con mensaje claro (no genera
  reporte vacío).
- Comprobantes en moneda extranjera → convertidos a moneda de compañía con
  el tipo de cambio del comprobante.

## Testing

- Tests Python (TransactionCase) sobre el AbstractModel:
  - Factura contado vs factura de partner con límite de crédito → columnas
    Contado / Cta.Cte y Cantid. CC.
  - NC contado y NC ctacte → N/C Cont. / N/C Dev.CtaCte del día.
  - Comprobante FCE (doc 201/206/211/203/208/213) → columnas MiPyme, con
    prioridad sobre la clasificación por partner.
  - Recibo de cobro del día → fila en Dev.CtaCte D/Ant.
  - Descuentos: % ponderado y monto.
  - Resolución de vendedor: invoice_user_id vs counter_salesperson_id
    (simulada con un campo de test si pos_centralized_payment no está).
  - Filtrado por fecha, estado posted y compañía.
- PDF y XLSX se verifican generándolos contra datos de prueba.

## Fuera de alcance

- Corregir `pos_centralized_payment` para que la factura tome al vendedor
  de mostrador como comercial (mejora separada en el repo pos_enhancements).
- Cobro de cuenta corriente desde el PDV (depósitos en sesión).
- Comparación contra arqueo físico de caja (eso lo cubre el reporte de
  Rendición de Caja del repo pos_enhancements).
