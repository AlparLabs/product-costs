# Chequeras compartidas entre diarios — Diseño

**Fecha:** 2026-09-23
**Repo/rama destino:** enhancement-suite / 19.0
**Módulo:** `account_journal_check_sequence` (19.0.1.2.0 → 19.0.1.3.0)

## Objetivo

Hoy la numeración de cheques propios vive dentro de cada diario de banco
(`check_sequence_enabled`, `next_check_number`, `check_number_padding` en
`account.journal`), así que cada diario tiene su propio contador (relación
1:1). El cliente que motiva este desarrollo tiene **muchas sucursales y
empresas, con varios diarios que emiten cheques de una misma chequera
física** y siguen la numeración correlativa entre todos. Esos diarios
pueden estar en la misma compañía o en compañías distintas. Necesitan que
todos consuman un único contador, sin números duplicados aunque publiquen
al mismo tiempo, y poder pasar a ese esquema sin configurar diario por
diario.

La solución es sacar el contador del diario a un modelo propio,
`account.checkbook`, y que los diarios lo referencien (relación N:1).

## Decisiones tomadas

- **Modelo propio, no `ir.sequence`.** El módulo espía el próximo número
  sin consumirlo, acepta que el usuario salte números a mano, reposiciona el
  contador en el número más alto emitido, nunca retrocede e infiere el
  prefijo/sufijo de lo que tipea el usuario. `ir.sequence` no modela nada de
  eso: habría que construirlo encima y además convivir con dos fuentes de
  verdad para el prefijo. Además `check_sequence_id` ya lo usa
  `account_check_printing`.
- **Tampoco un "diario maestro".** Descartado porque un diario pasaría a ser
  dueño del contador de los demás y en multicompañía quedaría atado a una
  compañía.
- **Una sola chequera por diario.** Esa chequera puede estar compartida con
  otros diarios. Un diario no tiene varias chequeras a la vez.
- **Sirve entre compañías.** Si `company_id` está vacío, la chequera se
  puede compartir entre compañías.
- **Tener chequera asignada equivale a tener la numeración activa.** Se
  elimina el booleano como fuente de verdad.
- **La migración no fusiona chequeras.** Crea una chequera por cada diario
  habilitado, porque no hay forma de saber qué diarios comparten chequera
  física. Para agruparlas se usa un **asistente de unificación**, que mueve
  en un solo paso los diarios y los cheques ya emitidos a la chequera
  destino.
- **Las columnas viejas no se borran** en esta versión y quedan como
  respaldo.
- **Un número ya emitido en la chequera no se puede volver a usar.** Se
  muestra un aviso en el formulario mientras se carga el pago y se bloquea
  con un `ValidationError` al publicar, sin importar desde qué diario o
  compañía se haya emitido el cheque anterior.

## Modelo `account.checkbook`

`_description = 'Chequera'`, `_order = 'name, id'`.

| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char, required | Ej. "Galicia – Serie B" |
| `next_number` | Char, `copy=False`, default `'00000001'` | Próximo número a sugerir; admite prefijo/sufijo (`E-00000100`) |
| `padding` | Integer, default `8` | Constraint 1..20 (`MAX_CHECK_NUMBER_PADDING`) |
| `company_id` | Many2one `res.company`, opcional | Vacío = compartible entre compañías |
| `journal_ids` | One2many `account.journal` / `checkbook_id` | Solo de lectura en la UI |
| `active` | Boolean, default `True` | Se archiva una chequera agotada |

**Lógica que se mueve desde `account.journal`, sin cambios de
comportamiento** (se reemplaza `next_check_number` por `next_number` y
`check_number_padding` por `padding`):

- `CHECK_NUMBER_RE`, `DEFAULT_CHECK_NUMBER_PADDING`,
  `MAX_CHECK_NUMBER_PADDING` (constantes de módulo)
- `_parse_check_number`, `_format_check_number`
- `_get_next_check_number_formatted`, `_calculate_next_number`
- `_peek_check_numbers`, `_get_highest_check_number`
- `_is_check_number_ahead`
- `_lock_and_read_next_check_number` → pasa a tomar el lock con un UPDATE
  sobre `account_checkbook` que no cambia el valor, sin `NOWAIT`. Ver
  "Números de cheque duplicados → Concurrencia".
- `_increment_check_number` → escribe con `sudo()`. Antes de avanzar el
  contador valida `active`: una chequera archivada no avanza.

Como el lock ahora es sobre la fila de la chequera, **serializa también los
posteos de diarios y compañías distintos** que comparten chequera.

## Cambios en `account.journal`

- `checkbook_id`: Many2one `account.checkbook`, `ondelete='restrict'`,
  `copy=False`, `check_company=False` (la compatibilidad de compañía se
  valida con la constraint de abajo, porque la chequera puede no tener
  compañía).
- `check_sequence_enabled`: pasa a ser un campo computado no almacenado =
  `bool(checkbook_id) and checkbook_id.active`. Se mantiene para no romper
  referencias externas.
- `next_check_number`: `related='checkbook_id.next_number'`,
  `readonly=False`.
- `check_number_padding`: `related='checkbook_id.padding'`,
  `readonly=False`.
- `checkbook_shared_journal_ids`: campo computado no almacenado con los
  otros diarios que usan la misma chequera (sin incluir el diario actual).
  Se usa para el aviso en la vista.
- Constraint `_check_checkbook_company`: si `checkbook_id.company_id` está
  definido y no es la compañía del diario ni una de sus compañías madre
  (`journal.company_id.parent_ids`, que incluye a la propia compañía), lanza
  `ValidationError`. Así una sucursal puede usar la chequera de su casa
  matriz. El dominio de `checkbook_id` acompaña con
  `('company_id', 'parent_of', company_id)`.
  La misma validación va en `account.checkbook` sobre `company_id` y
  `journal_ids`, para que cambiarle la compañía a una chequera en uso no
  deje combinaciones inválidas.
- Se eliminan del diario los métodos de secuencia (ahora están en la
  chequera) y la constraint de padding.

## Cambios en los consumidores

- `account.check.sequence.mixin`:
  - `_check_sequence_journal()` → `_check_sequence_checkbook()`. Devuelve
    `journal_id.checkbook_id` si la chequera está activa y el pago es
    `own_checks`. Si no, devuelve `account.checkbook` vacío.
  - `@api.depends` de `_compute_check_sequence_next_number` →
    `journal_id.checkbook_id.next_number`, `journal_id.checkbook_id.active`
    (se agrega `journal_id.checkbook_id`).
  - `_apply_check_sequence_suggestion` usa la chequera.
- `account.check.sequence.line.mixin._get_next_check_number_for_line`:
  usa `parent._check_sequence_checkbook()`.
- `account.payment.action_post`, en este orden:
  1. **Antes de `super()`**: toma el lock de las chequeras involucradas
     (`_lock_and_read_next_check_number`), ordenadas por id para evitar
     deadlocks. Ver "Números de cheque duplicados".
  2. `super().action_post()`: acá corre la validación de duplicados.
  3. Escribe `checkbook_id` en `l10n_latam_new_check_ids`.
  4. `checkbook._increment_check_number(
     checkbook._get_highest_check_number(used_numbers))`.
- `l10n_latam_check.py` y el wizard `account_payment_register.py`: se
  ajustan las llamadas al nuevo nombre del método. La lógica no cambia.
- Vistas de pago y wizard: sin cambios, siguen publicando
  `check_sequence_next_number` en el contexto.

## Números de cheque duplicados

**Qué cubre Odoo nativo y por qué no alcanza.** `l10n_latam.check` tiene
`UniqueIndex("(name, payment_method_line_id) WHERE outstanding_line_id IS
NOT NULL")`. Como cada diario tiene su propia `payment_method_line_id`, la
unicidad es **por diario**: el mismo número emitido desde dos diarios que
comparten chequera no se detecta. Además el usuario solo lo ve al publicar,
como error de base. El aviso amigable nativo
(`l10n_latam_check_warning_msg`) solo busca duplicados de cheques de
terceros.

**Chequera emisora en el cheque.** Se agrega a `l10n_latam.check` el campo
`checkbook_id` (Many2one `account.checkbook`, almacenado, `readonly=True`,
`copy=False`, `index=True`, `ondelete='restrict'`). Se escribe al publicar el pago. No se calcula a
partir de `journal_id.checkbook_id`, porque si un diario cambia de chequera
sus cheques viejos pasarían a la chequera nueva y darían falsos duplicados.

**Regla.** Un cheque propio de un pago en borrador choca si su `name`:
- ya existe en otro `l10n_latam.check` con el mismo `checkbook_id`, cuyo
  pago no esté en `draft` ni `canceled` (los anulados, `issue_state =
  'voided'`, cuentan: ese número ya se usó físicamente); o
- se repite en otra línea de `l10n_latam_new_check_ids` del mismo pago.

La comparación es por `name` exacto, después de aplicar el padding que ya
hace el módulo. Solo aplica si el pago tiene chequera (el resultado de
`_check_sequence_checkbook()`).

**Dónde se engancha.** Override de
`account.payment._get_blocking_l10n_latam_warning_msg`, que agrega un
mensaje por cada número repetido. Por ejemplo: "El cheque 00001050 de la
chequera «Galicia – Serie B» ya fue emitido en PAGO/2026/00123 (diario
Sucursal Centro)." Ese método nativo tiene dos usos, así que con un solo
override se cubre todo:
- `_compute_l10n_latam_check_warning_msg`: la alerta roja del formulario,
  que se recalcula al editar `l10n_latam_new_check_ids.name`.
- `action_post`: lanza `ValidationError` con los mensajes.

El wizard `account.payment.register` no tiene alerta propia. Los pagos que
genera pasan por `action_post`, así que igual quedan bloqueados con el
mismo mensaje.

**Concurrencia.** La validación corre dentro de `super().action_post()`.
Si el lock de la chequera se tomara después, dos sucursales que publican el
mismo número al mismo tiempo pasarían la validación las dos. Por eso
`action_post` toma el lock de la chequera **antes** de `super()`.

El lock no se toma con `SELECT ... FOR UPDATE` sino con un UPDATE que no
cambia nada:

```sql
UPDATE account_checkbook SET next_number = next_number WHERE id = %s RETURNING next_number
```

En PostgreSQL, un UPDATE genera una nueva versión de la fila aunque el
valor sea el mismo. Odoo trabaja en `REPEATABLE READ`, así que cualquier
otra transacción que esté esperando esa fila falla por serialización
cuando la primera confirma, y Odoo reintenta el request. En el reintento,
la validación ve el cheque ya publicado y bloquea.

Con `SELECT ... FOR UPDATE` esto no pasaría si la primera transacción no
avanzó el contador (por ejemplo, porque publicó un número más bajo). En
ese caso la segunda obtendría el lock sin error, seguiría con su snapshot
viejo y no vería el duplicado.

Este cambio reemplaza la consulta de `_lock_and_read_next_check_number`.
El incremento posterior no cambia: el recálculo sobre el valor ya
persistido sigue funcionando igual.

## Seguridad y multicompañía

`security/ir.model.access.csv` (nuevo):

| id | grupo | r | w | c | u |
|---|---|---|---|---|---|
| `access_account_checkbook_invoice` | `account.group_account_invoice` | 1 | 0 | 0 | 0 |
| `access_account_checkbook_manager` | `account.group_account_manager` | 1 | 1 | 1 | 1 |
| `access_account_checkbook_readonly` | `account.group_account_readonly` | 1 | 0 | 0 | 0 |

La fila de solo lectura hace falta porque en v19 `group_account_readonly` no
implica `group_account_invoice`: esos usuarios leen pagos y diarios, y los
campos computados no almacenados leen `checkbook_id.active` con su usuario.

`security/account_checkbook_security.xml`: record rule global
`['|', ('company_id', '=', False), ('company_id', 'parent_of', company_ids)]`,
igual que la regla nativa de `account.journal`: una sucursal ve las
chequeras de sus compañías madre.

El avance del contador al postear sigue haciéndose con `sudo()`, así que un
usuario de Facturación puede postear aunque no tenga permiso de escritura
sobre la chequera.

## Migración `19.0.1.3.0`

`migrations/19.0.1.3.0/post-migrate.py`. Usa el ORM con `SUPERUSER_ID`,
porque en v19 `account.journal.name` es jsonb traducible.

1. Si la columna `account_journal.check_sequence_enabled` no existe, no
   hace nada (es una instalación nueva).
2. Lee por SQL `id, company_id, next_check_number, check_number_padding` de
   `account_journal` con `check_sequence_enabled IS TRUE`, `type = 'bank'`
   y `checkbook_id IS NULL`.
3. Para cada diario crea `account.checkbook` con:
   - `name` = `journal.name`
   - `next_number` = `next_check_number` (o `'00000001'` si está vacío)
   - `padding` = `check_number_padding` (o 8 si es inválido)
   - `company_id` = `journal.company_id`

   Después asigna `checkbook_id`.
4. Completa `l10n_latam_check.checkbook_id` de los cheques propios ya
   emitidos (`outstanding_line_id IS NOT NULL`, código de método de pago
   `own_checks`) con la chequera del diario del pago. Se hace por SQL,
   joineando `account_payment`, `account_payment_method_line` y
   `account_payment_method`, y solo donde `checkbook_id IS NULL`. Así, el
   control de duplicados cubre también lo que se emitió antes de la
   actualización.
5. Loguea la cantidad de chequeras creadas y de cheques completados.

Es idempotente porque filtra `checkbook_id IS NULL`. Las columnas viejas
quedan en la base.

Después de actualizar, los diarios que ya numeraban de la misma chequera
física quedan con chequeras separadas. Se agrupan con el asistente de
unificación (sección siguiente).

## Asistente de unificación de chequeras

`wizards/account_checkbook_merge.py`: TransientModel
`account.checkbook.merge`, "Unificar chequeras".

**Por qué hace falta.** Sin el asistente, pasar muchos diarios a una sola
chequera es un trámite diario por diario. Además, si solo se reasigna el
diario, sus cheques ya emitidos quedan asociados a la chequera vieja y el
control de duplicados no los ve. Por ejemplo, la sucursal B emitió el 1040
con su chequera vieja; después de reasignar B, alguien de A tipea el 1040 y
no salta el aviso.

**Campos:**

| Campo | Tipo | Notas |
|---|---|---|
| `checkbook_ids` | Many2many `account.checkbook` | Default: `active_ids`. Mínimo 2. |
| `target_checkbook_id` | Many2one `account.checkbook`, required | Dominio: dentro de `checkbook_ids`. Default: la chequera con más diarios; si empatan, la de menor id. |
| `next_number` | Char, required | Default: `_get_highest_check_number` sobre los `next_number` de las seleccionadas. Es editable, por si las series tienen prefijos distintos. |
| `company_id` | Many2one `res.company`, computado | La compañía común de todos los diarios involucrados o, si son de varias, la compañía madre más cercana que compartan (por ejemplo, una compañía y sus sucursales). Si no comparten ninguna, queda vacío y la chequera destino se vuelve compartible entre todas las compañías. Sin diarios, se usa la compañía común de las chequeras. Se muestra como información. |
| `journal_ids` | Many2many, computado | Todos los diarios que van a quedar en la chequera destino. Informativo. |
| `duplicate_warning` | Text, computado | Números que se repiten en los cheques emitidos de las chequeras seleccionadas, con los pagos involucrados (mismo criterio que la regla de duplicados). Es solo informativo: no bloquea la unificación, porque es historia que ya ocurrió, pero conviene que el usuario la vea. |

**`action_merge`**, en una sola transacción:
1. Valida que haya al menos 2 chequeras y que la destino esté entre las
   seleccionadas.
2. Toma el lock de todas las chequeras seleccionadas, ordenadas por id, con
   el mismo UPDATE que se usa al publicar. Así ningún pago concurrente
   publica en el medio.
3. Escribe `company_id` en la chequera destino, según el valor computado,
   para que la constraint de compañía no rechace los diarios nuevos.
4. Reasigna los diarios de las otras chequeras: `checkbook_id` = destino.
5. Reasigna los cheques emitidos: `l10n_latam.check` con `checkbook_id` en
   las otras chequeras pasa a apuntar a la destino.
6. Escribe `next_number` en la chequera destino con el valor del asistente.
   Acá no se aplica la regla de "no retroceder": es una decisión explícita
   del usuario.
7. Archiva las chequeras de origen, que quedaron sin diarios.
8. Devuelve la acción que abre el formulario de la chequera destino.

**Acceso.** Solo `account.group_account_manager`. Se abre desde la acción
"Unificar chequeras" (`binding_model_id` = `account.checkbook`, vista de
lista).

## Seguridad del asistente

Se agrega a `ir.model.access.csv` la línea
`access_account_checkbook_merge_manager`, para
`account.group_account_manager`, con permisos 1,1,1,1.

## Vistas y menú

- `views/account_checkbook_views.xml` (nuevo):
  - Lista: `name`, `next_number`, `padding`, `company_id` (con
    `groups="base.group_multi_company"`), `journal_ids` (`many2many_tags`).
  - Formulario: los mismos campos, `journal_ids` en solo lectura y la
    ribbon de archivado.
  - Búsqueda: `name`, filtro "Sin diarios" (`journal_ids = False`) y
    filtro de archivadas.
- `wizards/account_checkbook_merge_views.xml` (nuevo): formulario del
  asistente y la acción con `binding_model_id` = `account.checkbook`
  (`binding_view_types="list"`). El formulario muestra la chequera destino,
  el próximo número, la compañía resultante, los diarios que van a quedar
  en la chequera y, si hay números repetidos en la historia, un
  `alert-warning` con `duplicate_warning`.
  - Acción y menú: Contabilidad → Configuración → Contabilidad →
    **Chequeras** (`account.account_account_menu`, al lado de Diarios; en
    v19 no hay submenú "Bancos"), visible solo para
    `account.group_account_manager`.
- `views/account_journal_views.xml`, grupo "Chequera / Numeración de
  Cheques Propios" (`invisible="type != 'bank'"`):
  - `checkbook_id` con `context="{'default_company_id': company_id}"`. La
    creación rápida crea la chequera con los defaults.
  - `next_check_number` y `check_number_padding` visibles solo si hay
    `checkbook_id`.
  - Si hay `checkbook_shared_journal_ids`, un `alert-info` que avisa: "Esta
    chequera también la usan:" seguido de los diarios. Si se cambia el
    próximo número, el cambio aplica a todos.

## Tests

`tests/test_check_sequence.py`:

- `setUp`: crea `self.checkbook` (`next_number='00001001'`) y la asigna a
  `self.bank_journal`.
- Los tests del contador (formato, incremento, salto manual, no retroceso,
  prefijo, cambio de serie, peek, más alto, lock, recálculo después del
  lock, padding) pasan a llamarse sobre `self.checkbook`. El `UPDATE` crudo
  del test de lock pasa a apuntar a `account_checkbook`.
- `check_sequence_enabled = False` se reemplaza por
  `self.bank_journal.checkbook_id = False`.
- Tests nuevos:
  - Dos diarios que comparten chequera: postear en A hace que B sugiera el
    número siguiente.
  - Una chequera sin compañía asignada a diarios de dos compañías: avanza
    correctamente desde ambas.
  - Una chequera de la compañía X asignada a un diario de la compañía Y
    lanza `ValidationError`.
  - Una chequera archivada no sugiere número y no avanza al postear.
  - Borrar una chequera en uso lanza un error (restrict).
  - Editar `next_check_number` desde el diario actualiza la chequera y se
    ve desde el otro diario.
  - Migración: con columnas viejas cargadas por SQL y `checkbook_id` nulo,
    `migrate(cr, '19.0.1.2.0')` crea la chequera con los valores
    correctos y completa `checkbook_id` en los cheques ya emitidos. Una
    segunda corrida no crea nada.
  - Duplicados:
    - Un número ya emitido desde el diario A, cargado en un pago del
      diario B con la misma chequera, muestra la alerta
      (`l10n_latam_check_warning_msg`) y `action_post` lanza
      `ValidationError`.
    - Dos líneas con el mismo número en el mismo pago también bloquean.
    - Un número usado en un pago cancelado o en borrador no bloquea.
    - Un número usado en una chequera distinta (incluida la chequera vieja
      de un diario que cambió de chequera) no bloquea.
    - Un cheque anulado (`voided`) sí bloquea.
    - Al publicar, se completa `checkbook_id` en los cheques.
    - Un pago en un diario sin chequera no aplica el control; queda solo
      el índice nativo.
  - Unificación:
    - Tres chequeras de diarios de dos compañías: después de unificar, todos
      los diarios apuntan a la destino, que queda sin compañía, y las otras
      dos quedan archivadas.
    - Los cheques emitidos de las chequeras de origen pasan a la destino.
      Un número que ya había emitido la sucursal B, tipeado después en un
      pago de la sucursal A, bloquea.
    - `next_number` por defecto es el más alto de las seleccionadas, y el
      valor editado se respeta aunque sea más bajo.
    - Si todos los diarios son de la misma compañía, la destino conserva
      esa compañía.
    - `duplicate_warning` informa los números repetidos en la historia sin
      impedir la unificación.
    - Con una sola chequera seleccionada, o con la destino fuera de la
      selección, lanza `UserError`.

## Manifiesto y documentación

- `version`: `19.0.1.3.0`.
- `data`: `security/ir.model.access.csv`,
  `security/account_checkbook_security.xml`,
  `views/account_checkbook_views.xml`,
  `wizards/account_checkbook_merge_views.xml`, más las vistas existentes.
- `summary` y `description`: pasan de "numeración por diario" a
  "chequeras, compartibles entre diarios y compañías".
- README:
  - Qué es una chequera y cómo compartirla.
  - La puesta en marcha después de actualizar: abrir Chequeras, seleccionar
    las de las sucursales que comparten chequera física, "Unificar
    chequeras" y revisar el próximo número y el aviso de duplicados.
  - El control de duplicados.
  - El comportamiento de una chequera archivada.
- Sin i18n: los strings del módulo ya están en castellano.

## Fuera de alcance

- Varias chequeras activas por diario, o elegir la chequera en cada pago.
- Rangos de numeración (desde/hasta) y aviso de chequera agotada.
- Borrar las columnas viejas de `account_journal`.
- Unificación automática de chequeras en la migración. Se hace con el
  asistente.
- Deshacer una unificación.
- Índice único en base por `(name, checkbook_id)`. El control queda a
  nivel aplicación, con el lock de la chequera para serializar. El índice
  nativo por diario se mantiene.
- Alerta propia en el wizard `account.payment.register`. El bloqueo sí
  aplica, porque los pagos que genera pasan por `action_post`.
