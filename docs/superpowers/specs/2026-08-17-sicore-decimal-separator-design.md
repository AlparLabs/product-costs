# Separador decimal configurable en TXT de liquidación de impuestos

**Fecha:** 2026-08-17
**Módulo:** `l10n_ar_settlement_decimal_separator`
**Ramas objetivo:** `18.0` primero, port inmediato a `19.0`

## Problema

El aplicativo SIAp – SI.CO.RE. permite configurar el separador decimal con el que lee
los archivos de importación de retenciones (`Importar/Exportar Retenciones/Percepciones`
→ `Configuración de Importación de Retenciones` → `Separador de decimales`).

Hasta el Release 22 el default era **coma**. A partir del Release 23 pasó a **punto**.
Muchos estudios contables tienen la opción fijada en coma a mano, o la arrastran de una
instalación anterior, y la configuración se resetea en cada actualización del aplicativo.

El TXT que genera `l10n_ar_account_tax_settlement` usa **punto**. Cuando el SICORE del
receptor está configurado en coma, el aplicativo no puede parsear los campos numéricos y
rechaza el archivo con el mensaje *"el campo X debería ser Numérico Positivo"*, repetido
para cuatro campos por cada línea del archivo.

### Diagnóstico verificado

Los cuatro campos que el aplicativo rechaza son exactamente los cuatro que contienen
punto decimal, generados en `l10n_ar_account_tax_settlement/models/account_journal.py`,
método `sicore_aplicado_files_values`:

| Campo SICORE | Ancho | Formato en el código |
|---|---|---|
| Importe del comprobante | 16 | `"%016.2f" % amount_tot` |
| Base de cálculo | 14 | `"%014.2f" % base_amount` |
| Importe de la retención | 14 | `"%014.2f" % abs(line.balance)` |
| Porcentaje de exclusión | 6 | `"%06.2f" % tax.porcentaje_exclusion` |

Los demás campos numéricos del registro (Nro. de comprobante, código de régimen, Nro. de
certificado original) **no** llevan punto y **no** son rechazados. Esto confirma que la
causa es el separador y no el contenido.

Un archivo de ejemplo del cliente (período 06/2026, 23 registros) se validó como
estructuralmente correcto: 145 caracteres por registro, terminador CRLF, ASCII.

## Solución

Un campo en `account.journal` que permita elegir el separador decimal del TXT, aplicado
en el único punto de dispatch que ya existe en el módulo base.

**El archivo generado por Odoo es correcto.** La solución correcta para el usuario final
sigue siendo configurar el SICORE en "punto". Este módulo es la vía de escape para los
casos en que el receptor del archivo no modifica su configuración.

## Alcance

### Incluido

- Campo `Selection` punto/coma en `account.journal`, default punto.
- Aplicación mediante lista blanca de tipos de liquidación, inicialmente solo
  `sicore_aplicado`.
- Tests que cubren el comportamiento por defecto, el reemplazo, el ancho fijo y los
  casos fuera de la lista blanca.

### Excluido, con motivo

- **Separador libre (`Char`)**: descartado. Un separador de más de un carácter rompe el
  ancho fijo del registro. Un carácter arbitrario (`;`, `|`) genera archivos que ningún
  aplicativo acepta. El SICORE solo ofrece punto y coma.
- **"Sin separador"** (decimales implícitos, estilo Libro IVA Digital): descartado.
  No es un reemplazo sino un acortamiento del campo (14 → 13), que exigiría re-paddear.
  Ningún régimen que salga de este dispatch lo pide.
- **Otros `settlement_tax`**: no se incluyen hasta validar que su TXT no tiene campos de
  texto libre. Ver "Por qué lista blanca".
- **El bug de precedencia en `account_journal.py:1314`** de ADHOC
  (`"%06.2f" % tax.porcentaje_exclusion or "000.00"`: `%` liga más fuerte que `or`, así
  que el fallback nunca actúa como se pretende): detectado, no se corrige. Es código de
  ADHOC y no afecta a este desarrollo.

### Por qué lista blanca y no aplicación global

El reemplazo se hace sobre el contenido completo del archivo. En SICORE es seguro porque
todos los campos son numéricos o fechas con `/`; no hay texto libre.

Otros TXT generados por el mismo dispatch sí lo tienen. `l10n_ar_txt_sire` escribe
`partner_id.name` y el domicilio del contacto. Un reemplazo global corrompería
"ACME S.A." o "Av. Rivadavia 1234".

La lista blanca permite un hook genérico sin ese riesgo. Sumar SIFERE o SIRCAR más
adelante es agregar un elemento a la constante, una vez verificado que su formato no
tiene texto libre.

## Diseño técnico

### Manifest

```python
{
    "name": "Separador decimal configurable en TXT de liquidación",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": "Permite exportar los TXT de liquidación con punto o coma decimal",
    "author": "AlparData",
    "website": "https://www.alpardata.com.ar",
    "license": "OEEL-1",
    "depends": ["l10n_ar_account_tax_settlement"],
    "data": ["views/account_journal_views.xml"],
    "installable": True,
    "auto_install": False,
}
```

La dependencia es `l10n_ar_account_tax_settlement` (no el base `account_tax_settlement`)
porque la lista blanca referencia `sicore_aplicado`, valor de `settlement_tax` que se
define en ese módulo.

No se modifica ningún archivo del repositorio `odoo-argentina-ee`. Su código queda
actualizable.

### Modelo

`models/account_journal.py`:

```python
L10N_AR_SEPARATOR_SAFE_SETTLEMENTS = ["sicore_aplicado"]


class AccountJournal(models.Model):
    _inherit = "account.journal"

    l10n_ar_txt_decimal_separator = fields.Selection(
        [(".", "Punto (.)"), (",", "Coma (,)")],
        string="Separador decimal del TXT",
        default=".",
        help="Separador decimal con el que se generan los importes del archivo TXT. "
             "Debe coincidir con el configurado en el aplicativo que va a importarlo. "
             "En el SICORE se define en Importar/Exportar Retenciones/Percepciones → "
             "Configuración de Importación de Retenciones.",
    )

    def get_tax_settlement_files_values(self, move_lines):
        files_values = super().get_tax_settlement_files_values(move_lines)
        separator = self.l10n_ar_txt_decimal_separator or "."
        if separator == "." or self.settlement_tax not in L10N_AR_SEPARATOR_SAFE_SETTLEMENTS:
            return files_values
        for values in files_values:
            content = values.get("txt_content")
            if isinstance(content, str):
                values["txt_content"] = content.replace(".", separator)
        return files_values
```

Tres guardas antes de modificar nada:

1. Separador en punto o `NULL` → se devuelve el resultado de `super()` sin tocar.
2. `settlement_tax` fuera de la lista blanca → sin tocar.
3. `txt_content` que no sea `str` → sin tocar.

`txt_filename` no se modifica nunca: `"SICORE Aplicado.txt"` contiene un punto en la
extensión.

El ancho fijo se preserva por construcción, porque el reemplazo es de un carácter por
otro.

### Punto de enganche

`account_tax_settlement/models/account_journal.py:311`:

```python
def get_tax_settlement_files_values(self, move_lines):
    ...
    if self.settlement_tax and hasattr(self, "%s_files_values" % self.settlement_tax):
        return getattr(self, "%s_files_values" % self.settlement_tax)(move_lines)
    return []
```

Es el único dispatch de los ~20 métodos `*_files_values`. Overridearlo evita duplicar
lógica y sobrevive a que ADHOC agregue nuevos tipos de liquidación.

### Vista

`views/account_journal_views.xml`, heredando
`account_tax_settlement.view_account_journal_form`:

```xml
<field name="settlement_tax" position="after">
    <field name="l10n_ar_txt_decimal_separator"
           invisible="settlement_tax not in ['sicore_aplicado']"/>
</field>
```

El campo queda oculto en los diarios que no son de liquidación SICORE.

### Migración de datos

Ninguna. Los diarios existentes quedan con el campo en `NULL` (el `default` de Odoo solo
aplica a registros nuevos) y el código trata `NULL` como punto. Instalar el módulo no
altera la salida de ninguna instancia existente.

## Tests

`tests/test_decimal_separator.py`, `TransactionCase`, consistente con
`account_payment_lock_3way` y los demás módulos del repo que ya tienen tests.

1. **Default sin efecto**: diario `sicore_aplicado` con el campo en su valor por defecto
   produce contenido idéntico al de `super()`. Es el test de regresión que garantiza que
   instalar el módulo no rompe a ningún cliente actual.
2. **Reemplazo con coma**: con el campo en coma, el contenido no contiene ningún `.` y
   cada línea sigue midiendo 145 caracteres.
3. **Fuera de la lista blanca**: diario con `settlement_tax` distinto de
   `sicore_aplicado` y el campo en coma produce contenido sin modificar.
4. **Campo en `NULL`**: se comporta igual que punto.
5. **Filename intacto**: `txt_filename` no se modifica en ninguno de los casos
   anteriores.

## Riesgos

- **Cambio de firma aguas arriba**: si ADHOC modifica la firma de
  `get_tax_settlement_files_values`, el override deja de aplicar. Riesgo bajo: el método
  es estable y el test 1 lo detectaría.
- **Ampliación descuidada de la lista blanca**: agregar un `settlement_tax` cuyo TXT
  tenga campos de texto libre corrompería nombres y domicilios. Mitigación: la constante
  lleva un comentario que exige verificar el formato antes de sumar un tipo.

## Plan de entrega

1. Implementar y testear en la rama `18.0`.
2. Portar a `19.0`. El punto de enganche es idéntico en ambas ramas de
   `odoo-argentina-ee`, por lo que el código es portable casi verbatim; lo que se
   revalida es la suite de tests en el entorno 19.
3. Validar contra el SICORE real del cliente: el archivo con coma debe importar sin
   errores.

El cliente está en 18 y su migración a 19 está prevista, así que ambas ramas se entregan
juntas. La validación del paso 3 es la única prueba que cuenta —que el aplicativo del
contador acepte el archivo— y cualquier corrección que surja de ella se aplica a las dos
ramas.
