# Chequeras compartidas entre diarios: plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan checkboxes (`- [ ]`) para el seguimiento.

**Objetivo:** Sacar el contador de cheques propios de `account.journal` a un modelo `account.checkbook` que varios diarios (incluso de distintas compañías) comparten. También bloquear números ya emitidos en la misma chequera y proveer un asistente para unificar chequeras.

**Arquitectura:**
- `account.checkbook` absorbe toda la lógica de numeración que hoy vive en `account.journal`: parseo, peek, no retroceso y lock.
- El diario pasa a tener un Many2one `checkbook_id`. Sus campos actuales quedan como `related` para mantener la edición en el mismo formulario.
- Cada `l10n_latam.check` guarda al publicar la chequera que lo emitió. El control de duplicados se engancha en el método nativo `_get_blocking_l10n_latam_warning_msg`, que alimenta tanto la alerta del formulario como el bloqueo en `action_post`.
- Un TransientModel `account.checkbook.merge` mueve diarios y cheques emitidos a una chequera destino.

**Stack:** Odoo 19, módulo `account_journal_check_sequence`. Depende de `account` y `l10n_latam_check`.

**Spec:** `docs/superpowers/specs/2026-09-23-shared-checkbook-design.md`

---

## Cómo verificar (leer antes de empezar)

**En el entorno de desarrollo no hay una instancia de Odoo que se pueda ejecutar.** Solo está el código fuente en `C:\Users\Santiago\Desktop\Odoo\odoo-19.0`. Por eso cada tarea se verifica en dos niveles, y hay que reportar explícitamente cuál se corrió:

1. **Local (obligatorio en cada tarea):** compilar el Python y validar el XML.

   ```bash
   python -m compileall -q account_journal_check_sequence && echo PY_OK
   ```

   ```bash
   python -c "import glob,lxml.etree as E; [E.parse(f) for f in glob.glob('account_journal_check_sequence/**/*.xml', recursive=True)]; print('XML_OK')"
   ```

   Las vistas `list` y `search` además se validan contra el RelaxNG de Odoo 19. El `form` no tiene RNG en v19. Guardar este script **fuera del repo** (en un directorio temporal) como `validate_views.py` y ejecutarlo con `python <ruta>/validate_views.py`:

   ```python
   import glob
   from lxml import etree

   RNG_DIR = r'C:\Users\Santiago\Desktop\Odoo\odoo-19.0\odoo\addons\base\rng'
   ok = True
   for path in glob.glob('account_journal_check_sequence/**/*.xml', recursive=True):
       for arch in etree.parse(path).iterfind('.//field[@name="arch"]'):
           root = arch[0] if len(arch) else None
           if root is None or root.tag not in ('list', 'search'):
               continue
           rng = etree.RelaxNG(etree.parse(f'{RNG_DIR}\\{root.tag}_view.rng'))
           if not rng.validate(root):
               ok = False
               print(path, root.tag, rng.error_log)
   print('RNG_OK' if ok else 'RNG_FAIL')
   ```

2. **Tests de Odoo:** corren en una base de desarrollo (Odoo.sh o una instancia local del equipo):

   ```bash
   odoo-bin -d <base_dev> -u account_journal_check_sequence --test-enable --test-tags /account_journal_check_sequence --stop-after-init --log-level=test
   ```

   Los pasos que dicen "Correr los tests" usan este comando. Si no hay instancia disponible, **no marcar el paso como verificado**: dejarlo anotado como pendiente en el reporte de la tarea.

**Estilo del módulo:** docstrings y strings en castellano, sin i18n. Hay un comentario por cada decisión no obvia, como en `account_journal.py`. Cada commit termina con:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

**Nota sobre la spec:** en Odoo 19 no existe un menú "Configuración → Bancos". La chequera cuelga de **Contabilidad → Configuración → Contabilidad** (`account.account_account_menu`), al lado de Diarios. La Tarea 7 corrige esto en la spec.

## Mapa de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `models/account_checkbook.py` | Crear | Modelo chequera: campos, constraints, parseo/formato/peek, lock e incremento. |
| `models/account_journal.py` | Reescribir | `checkbook_id`, campos related/computados, constraint de compañía. Ya no contiene lógica de numeración. |
| `models/account_check_sequence_mixin.py` | Modificar | `_check_sequence_journal` pasa a `_check_sequence_checkbook`. |
| `models/account_check_sequence_line_mixin.py` | Modificar | Usa la chequera. |
| `models/account_payment.py` | Modificar | Lock antes de `super()`, `checkbook_id` en los cheques, control de duplicados. |
| `models/l10n_latam_check.py` | Modificar | Campo `checkbook_id`. |
| `models/__init__.py` | Modificar | Importa `account_checkbook`. |
| `wizards/account_checkbook_merge.py` | Crear | Asistente de unificación. |
| `wizards/account_checkbook_merge_views.xml` | Crear | Formulario y acción del asistente. |
| `wizards/__init__.py` | Modificar | Importa el asistente. |
| `security/ir.model.access.csv` | Crear | Accesos de la chequera y del asistente. |
| `security/account_checkbook_security.xml` | Crear | Regla multicompañía. |
| `views/account_checkbook_views.xml` | Crear | Lista, formulario, búsqueda, acción y menú. |
| `views/account_journal_views.xml` | Modificar | Grupo "Chequera" del diario. |
| `migrations/19.0.1.3.0/post-migrate.py` | Crear | Chequera por diario y backfill de cheques. |
| `__manifest__.py` | Modificar | Versión, `data`, descripción. |
| `README.md` | Modificar | Documentación funcional. |
| `tests/common.py` | Crear | Base de tests con chequera y diario. |
| `tests/test_checkbook.py` | Crear | Contador de la chequera y comportamiento compartido. |
| `tests/test_check_sequence.py` | Modificar | Flujos existentes adaptados a la chequera. |
| `tests/test_check_duplicates.py` | Crear | Control de duplicados. |
| `tests/test_migration.py` | Crear | Migración. |
| `tests/test_checkbook_merge.py` | Crear | Asistente. |
| `tests/__init__.py` | Modificar | Importa los tests nuevos. |

En la spec, todos los tests estaban en `test_check_sequence.py`. Acá se reparten en archivos por responsabilidad y la cobertura no cambia.

---

### Tarea 1: Modelo `account.checkbook` con la lógica del contador

**Archivos:**
- Crear: `account_journal_check_sequence/models/account_checkbook.py`
- Modificar: `account_journal_check_sequence/models/__init__.py`
- Crear: `account_journal_check_sequence/security/ir.model.access.csv`
- Crear: `account_journal_check_sequence/security/account_checkbook_security.xml`
- Modificar: `account_journal_check_sequence/__manifest__.py` (`data`)
- Crear: `account_journal_check_sequence/tests/test_checkbook.py`
- Modificar: `account_journal_check_sequence/tests/__init__.py`

En esta tarea el diario todavía conserva sus campos y métodos. La chequera existe al lado y no la usa nadie, así que el módulo sigue funcionando igual.

- [ ] **Paso 1: Escribir los tests del contador sobre la chequera**

Crear `account_journal_check_sequence/tests/test_checkbook.py`:

```python
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestCheckbookCounter(AccountTestInvoicingCommon):
    """Lógica de numeración de la chequera, sin pagos de por medio."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.checkbook = cls.env['account.checkbook'].create({
            'name': 'Chequera Test',
            'next_number': '00001001',
            'padding': 8,
        })

    def test_format(self):
        """El próximo número se formatea con el padding configurado."""
        self.assertEqual(self.checkbook._get_next_check_number_formatted(), '00001001')

    def test_increment(self):
        """El contador avanza uno respecto del número emitido."""
        self.checkbook._increment_check_number('00001001')
        self.assertEqual(self.checkbook.next_number, '00001002')

    def test_manual_skip(self):
        """Si el usuario saltea números, el contador arranca desde el usado."""
        self.checkbook._increment_check_number('00001050')
        self.assertEqual(self.checkbook.next_number, '00001051')

    def test_never_goes_backwards(self):
        """Postear un cheque anterior no debe hacer retroceder el contador."""
        self.checkbook._increment_check_number('00000500')
        self.assertEqual(
            self.checkbook.next_number, '00001001',
            'El contador no puede retroceder: llevaría a sugerir números ya emitidos.',
        )

    def test_with_prefix(self):
        """Se preserva el prefijo de la serie (ej. Echeqs 'E-00000100')."""
        self.checkbook.next_number = 'E-00000100'
        self.checkbook._increment_check_number('E-00000100')
        self.assertEqual(self.checkbook.next_number, 'E-00000101')

    def test_series_change_allowed(self):
        """Un cambio de serie (otro prefijo) sí puede reposicionar el contador."""
        self.checkbook._increment_check_number('E-00000100')
        self.assertEqual(self.checkbook.next_number, 'E-00000101')

    def test_peek_does_not_persist(self):
        """Consultar los próximos números no modifica la chequera."""
        self.assertEqual(self.checkbook._peek_check_numbers(3), ['00001001', '00001002', '00001003'])
        self.assertEqual(self.checkbook.next_number, '00001001')

    def test_highest_check_number(self):
        """El número más alto se resuelve por valor numérico, no por posición."""
        self.assertEqual(
            self.checkbook._get_highest_check_number(['00001003', '00001010', '00001005']),
            '00001010',
        )

    def test_lock_reads_persisted_value(self):
        """El lock devuelve el valor en base y descarta la cache en memoria."""
        self.checkbook.next_number = '00001007'
        self.assertEqual(self.checkbook._lock_and_read_next_check_number(), '00001007')

    def test_increment_recalculates_after_lock(self):
        """Tras tomar el lock, el contador se evalúa sobre el valor real en base.

        Simula al segundo pago concurrente: la chequera ya avanzó en base y la
        cache del recordset quedó vieja. El lock invalida esa cache, así que el
        retroceso se detecta y el contador no se pisa.
        """
        self.checkbook.flush_recordset(['next_number'])
        self.env.cr.execute(
            "UPDATE account_checkbook SET next_number = '00001010' WHERE id = %s",
            (self.checkbook.id,),
        )
        self.checkbook._increment_check_number('00001001')
        self.assertEqual(self.checkbook.next_number, '00001010')

    def test_lock_checkbooks_locks_every_record(self):
        """Bloquear varias chequeras deja a cada una con su valor en base."""
        other = self.checkbook.copy({'name': 'Otra', 'next_number': '00000050'})
        (self.checkbook | other)._lock_checkbooks()
        self.assertEqual(other.next_number, '00000050')
        self.assertEqual(self.checkbook.next_number, '00001001')

    def test_archived_checkbook_does_not_advance(self):
        """Una chequera archivada no avanza al postear."""
        self.checkbook.active = False
        self.checkbook._increment_check_number('00001001')
        self.assertEqual(self.checkbook.next_number, '00001001')

    def test_padding_constraint(self):
        """La cantidad de dígitos está acotada."""
        with self.assertRaises(ValidationError):
            self.checkbook.padding = 99
```

Modificar `account_journal_check_sequence/tests/__init__.py`:

```python
from . import test_check_sequence
from . import test_checkbook
```

- [ ] **Paso 2: Correr los tests y verificar que fallan**

Correr los tests (comando de "Cómo verificar").
Esperado: FALLA. El registry no conoce el modelo `account.checkbook` (`KeyError: 'account.checkbook'`).

- [ ] **Paso 3: Crear el modelo**

Crear `account_journal_check_sequence/models/account_checkbook.py`:

```python
import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Separa un número de cheque en prefijo, cuerpo numérico y sufijo
# (ej. 'E-00000100' -> 'E-', '00000100', '').
CHECK_NUMBER_RE = re.compile(r'^(.*?)(\d+)(\D*)$')

DEFAULT_CHECK_NUMBER_PADDING = 8
MAX_CHECK_NUMBER_PADDING = 20


class AccountCheckbook(models.Model):
    """Chequera de cheques propios.

    Tiene el contador que antes vivía en cada diario de banco. Varios diarios
    pueden apuntar a la misma chequera y consumen un único correlativo; si
    ``company_id`` está vacío, esos diarios pueden ser de compañías distintas.
    """

    _name = 'account.checkbook'
    _description = 'Chequera'
    _order = 'name, id'

    name = fields.Char(string='Nombre', required=True)
    next_number = fields.Char(
        string='Próximo Número de Cheque',
        copy=False,
        default='00000001',
        help='Número del siguiente cheque propio a sugerir en pagos u órdenes de pago.',
    )
    padding = fields.Integer(
        string='Dígitos del Cheque',
        default=DEFAULT_CHECK_NUMBER_PADDING,
        help='Cantidad de dígitos con ceros a la izquierda para formatear el número de cheque (ej. 8 para 00000001).',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        help='Vacío: la chequera se puede compartir entre diarios de distintas compañías.',
    )
    active = fields.Boolean(default=True)

    @api.constrains('padding')
    def _check_padding(self):
        for checkbook in self:
            if checkbook.padding and not (1 <= checkbook.padding <= MAX_CHECK_NUMBER_PADDING):
                raise ValidationError(_(
                    'La cantidad de dígitos de la chequera "%(checkbook)s" debe estar entre 1 y %(maximum)s.',
                    checkbook=checkbook.display_name,
                    maximum=MAX_CHECK_NUMBER_PADDING,
                ))

    # -------------------------------------------------------------------------
    # Helpers de parseo / formateo
    # -------------------------------------------------------------------------

    @api.model
    def _parse_check_number(self, value):
        """Descompone un número de cheque.

        :return: tupla ``(prefijo, valor_entero, largo_digitos, sufijo)`` o
            ``None`` si el valor no contiene ninguna parte numérica.
        """
        if not value:
            return None
        match = CHECK_NUMBER_RE.match(str(value).strip())
        if not match:
            return None
        prefix, digits, suffix = match.groups()
        return prefix, int(digits), len(digits), suffix

    def _format_check_number(self, prefix, value, digits_length, suffix):
        """Rearma un número aplicando el padding configurado en la chequera."""
        self.ensure_one()
        padding = max(self.padding or DEFAULT_CHECK_NUMBER_PADDING, digits_length)
        return f"{prefix}{str(value).zfill(padding)}{suffix}"

    # -------------------------------------------------------------------------
    # Cálculo de la secuencia
    # -------------------------------------------------------------------------

    def _get_next_check_number_formatted(self):
        """Devuelve el próximo número formateado según el padding configurado."""
        self.ensure_one()
        parsed = self._parse_check_number(self.next_number or '1')
        if not parsed:
            return (self.next_number or '').strip()
        return self._format_check_number(*parsed)

    def _calculate_next_number(self, base_number=None):
        """Calcula el siguiente número a partir de un valor base sin persistir nada."""
        self.ensure_one()
        base = base_number or self.next_number or '0'
        parsed = self._parse_check_number(base)
        if not parsed:
            return base_number or self.next_number
        prefix, value, digits_length, suffix = parsed
        return self._format_check_number(prefix, value + 1, digits_length, suffix)

    def _peek_check_numbers(self, count, start_from=False):
        """Devuelve ``count`` números correlativos sin modificar el contador.

        :param start_from: último número ya usado; si no se indica, se arranca
            desde el próximo número configurado en la chequera.
        """
        self.ensure_one()
        numbers = []
        last_number = start_from
        for _index in range(count):
            if last_number:
                last_number = self._calculate_next_number(last_number)
            else:
                last_number = self._get_next_check_number_formatted()
            numbers.append(last_number)
        return numbers

    def _get_highest_check_number(self, numbers):
        """Devuelve el número de mayor valor numérico de la lista recibida."""
        self.ensure_one()
        highest = False
        highest_value = None
        for number in numbers:
            parsed = self._parse_check_number(number)
            if not parsed:
                continue
            if highest_value is None or parsed[1] > highest_value:
                highest_value = parsed[1]
                highest = number
        if highest:
            return highest
        return numbers[-1] if numbers else False

    def _is_check_number_ahead(self, candidate):
        """Indica si ``candidate`` avanza respecto del contador actual.

        Evita que el contador retroceda cuando se postea un pago viejo o un
        cheque con un número inferior al ya alcanzado, lo que llevaría a
        sugerir números duplicados. Si cambia la serie (prefijo o sufijo
        distinto) se asume un cambio de chequera y se acepta el valor.
        """
        self.ensure_one()
        current = self._parse_check_number(self.next_number)
        new = self._parse_check_number(candidate)
        if not current or not new:
            return True
        if (current[0], current[3]) != (new[0], new[3]):
            return True
        return new[1] > current[1]

    # -------------------------------------------------------------------------
    # Concurrencia
    # -------------------------------------------------------------------------

    def _lock_and_read_next_check_number(self):
        """Toma un lock exclusivo sobre la fila de la chequera y devuelve el valor en base.

        El lock se toma con un UPDATE que no cambia el valor, y no con
        ``SELECT ... FOR UPDATE``. En PostgreSQL el UPDATE genera una versión
        nueva de la fila aunque el valor sea el mismo; como Odoo trabaja en
        REPEATABLE READ, cualquier transacción que esté esperando esta fila
        falla por serialización cuando la nuestra confirma, y Odoo reintenta
        el request. En el reintento ya ve los cheques publicados, así que el
        control de duplicados los detecta. Con ``FOR UPDATE`` eso solo pasaría
        si además avanzamos el contador: publicar un número más bajo que el
        contador dejaría pasar un duplicado concurrente.

        Sin ``NOWAIT`` a propósito: el segundo pago espera en vez de fallar.

        Se invalida la cache para que las lecturas posteriores de
        ``next_number`` vean el valor real y no el que quedó en memoria antes
        de esperar el lock.
        """
        self.ensure_one()
        self.flush_recordset(['next_number'])
        self.env.cr.execute(
            'UPDATE account_checkbook SET next_number = next_number WHERE id = %s RETURNING next_number',
            (self.id,),
        )
        row = self.env.cr.fetchone()
        self.invalidate_recordset(['next_number'])
        return row[0] if row else False

    def _lock_checkbooks(self):
        """Bloquea varias chequeras de a una y en orden de id, para no generar deadlocks."""
        for checkbook in self.sorted('id'):
            checkbook._lock_and_read_next_check_number()

    def _increment_check_number(self, used_number=None):
        """Avanza el contador en base al número efectivamente emitido.

        Se usa ``sudo()`` porque la escritura sobre ``account.checkbook`` está
        reservada a ``account.group_account_manager`` y quien postea el pago
        puede ser un usuario de Facturación.
        """
        self.ensure_one()
        if not self.active:
            return
        # Serializa el avance del contador entre pagos publicados en paralelo.
        self._lock_and_read_next_check_number()
        candidate = self._calculate_next_number(used_number)
        if not candidate or candidate == self.next_number:
            return
        if not self._is_check_number_ahead(candidate):
            _logger.info(
                'Chequera %s: se ignora el retroceso de la secuencia de cheques '
                '(actual: %s, calculado: %s).',
                self.display_name, self.next_number, candidate,
            )
            return
        self.sudo().next_number = candidate
```

Modificar `account_journal_check_sequence/models/__init__.py`:

```python
from . import account_check_sequence_mixin
from . import account_check_sequence_line_mixin
from . import account_checkbook
from . import account_journal
from . import account_payment
from . import l10n_latam_check
```

- [ ] **Paso 4: Crear la seguridad**

Crear `account_journal_check_sequence/security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_account_checkbook_invoice,account.checkbook.invoice,model_account_checkbook,account.group_account_invoice,1,0,0,0
access_account_checkbook_manager,account.checkbook.manager,model_account_checkbook,account.group_account_manager,1,1,1,1
```

Crear `account_journal_check_sequence/security/account_checkbook_security.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!--
        Una chequera sin compañía se comparte entre compañías: la ven todos
        los usuarios que tengan acceso al modelo.
    -->
    <record id="account_checkbook_company_rule" model="ir.rule">
        <field name="name">Chequera: multicompañía</field>
        <field name="model_id" ref="model_account_checkbook"/>
        <field name="domain_force">['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]</field>
    </record>
</odoo>
```

En `account_journal_check_sequence/__manifest__.py`, reemplazar la clave `data` por:

```python
    'data': [
        'security/ir.model.access.csv',
        'security/account_checkbook_security.xml',
        'views/account_journal_views.xml',
        'views/account_payment_views.xml',
    ],
```

- [ ] **Paso 5: Verificación local**

Correr `compileall` y la validación de XML (ver "Cómo verificar").
Esperado: `PY_OK` y `XML_OK`.

- [ ] **Paso 6: Correr los tests y verificar que pasan**

Correr los tests.
Esperado: PASA. Los 13 tests de `TestCheckbookCounter` y los de `test_check_sequence.py` siguen en verde.

- [ ] **Paso 7: Commit**

```bash
git add account_journal_check_sequence/models/account_checkbook.py account_journal_check_sequence/models/__init__.py account_journal_check_sequence/security account_journal_check_sequence/__manifest__.py account_journal_check_sequence/tests/test_checkbook.py account_journal_check_sequence/tests/__init__.py
git commit -m "feat(account_journal_check_sequence): modelo account.checkbook con la lógica del contador" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 2: El diario apunta a la chequera y los consumidores la usan

**Archivos:**
- Reescribir: `account_journal_check_sequence/models/account_journal.py`
- Modificar: `account_journal_check_sequence/models/account_checkbook.py` (`journal_ids` y constraint de compañía)
- Modificar: `account_journal_check_sequence/models/account_check_sequence_mixin.py`
- Modificar: `account_journal_check_sequence/models/account_check_sequence_line_mixin.py`
- Modificar: `account_journal_check_sequence/models/account_payment.py`
- Crear: `account_journal_check_sequence/tests/common.py`
- Modificar: `account_journal_check_sequence/tests/test_check_sequence.py`
- Modificar: `account_journal_check_sequence/tests/test_checkbook.py`

- [ ] **Paso 1: Crear la base común de tests**

Crear `account_journal_check_sequence/tests/common.py`:

```python
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class CheckbookTestCommon(AccountTestInvoicingCommon):
    """Diario de banco con método Cheque Propio y una chequera asignada."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.checkbook = cls.env['account.checkbook'].create({
            'name': 'Chequera Test',
            'next_number': '00001001',
            'padding': 8,
        })
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.bank_journal.checkbook_id = cls.checkbook
        cls.outstanding_account = cls.outbound_payment_method_line.payment_account_id
        cls.own_checks_line = cls._setup_own_checks_line(cls.bank_journal, cls.outstanding_account)
        cls.check_date = fields.Date.add(fields.Date.today(), months=1)

    @classmethod
    def _setup_own_checks_line(cls, journal, outstanding_account):
        """Agrega el método Cheque Propio al diario y devuelve su línea."""
        journal.outbound_payment_method_line_ids = [
            Command.create({
                'payment_method_id': cls.env.ref('l10n_latam_check.account_payment_method_own_checks').id,
                'name': 'Own Checks',
            }),
        ]
        line = journal.outbound_payment_method_line_ids.filtered(lambda method: method.code == 'own_checks')
        line.payment_account_id = outstanding_account
        return line

    @classmethod
    def _setup_second_company(cls):
        """Crea una segunda compañía y la deja activa junto con la primera.

        Sin ``allowed_company_ids`` las reglas multicompañía ocultan los
        registros de la compañía 2 (chequeras, diarios, cheques). Los registros
        de clase se vuelven a leer con el entorno nuevo.
        """
        cls.company_data_2 = cls.setup_other_company()
        cls.company_2 = cls.company_data_2['company']
        cls.env = cls.env(context=dict(
            cls.env.context,
            allowed_company_ids=(cls.company_data['company'] | cls.company_2).ids,
        ))
        cls.checkbook = cls.env['account.checkbook'].browse(cls.checkbook.id)
        cls.bank_journal = cls.env['account.journal'].browse(cls.bank_journal.id)
        cls.own_checks_line = cls.env['account.payment.method.line'].browse(cls.own_checks_line.id)
        cls.outstanding_account_2 = cls.outstanding_account.copy({
            'company_ids': [Command.set(cls.company_2.ids)],
        })

    @classmethod
    def _create_bank_journal(cls, name, code, company=None, checkbook=None):
        company = company or cls.company_data['company']
        return cls.env['account.journal'].with_company(company).create({
            'name': name,
            'code': code,
            'type': 'bank',
            'company_id': company.id,
            'checkbook_id': checkbook.id if checkbook else False,
        })

    def _create_own_check_payment(self, checks_vals, journal=None, own_checks_line=None):
        journal = journal or self.bank_journal
        own_checks_line = own_checks_line or self.own_checks_line
        return self.env['account.payment'].with_company(journal.company_id).create({
            'payment_type': 'outbound',
            'partner_id': self.partner_a.id,
            'journal_id': journal.id,
            'payment_method_line_id': own_checks_line.id,
            'l10n_latam_new_check_ids': [Command.create(vals) for vals in checks_vals],
        })
```

- [ ] **Paso 2: Adaptar `test_check_sequence.py` a la base común**

En `account_journal_check_sequence/tests/test_check_sequence.py`:

1. Reemplazar todo desde la primera línea hasta el final de `_create_own_check_payment` (líneas 1-38 actuales) por:

```python
# account_journal_check_sequence/tests/test_check_sequence.py
from odoo.tests import Form, tagged

from .common import CheckbookTestCommon


@tagged('post_install', '-at_install')
class TestCheckSequence(CheckbookTestCommon):
```

2. Borrar la sección "Formateo y cálculo" completa: desde el comentario `# Formateo y cálculo` hasta el final de `test_padding_constraint` (líneas 41-116 actuales). Esos tests ya están en `test_checkbook.py`.

3. En `test_create_on_disabled_journal`, `test_next_number_empty_out_of_scope` y `test_action_post_on_disabled_journal`, reemplazar la línea

```python
        self.bank_journal.check_sequence_enabled = False
```

por

```python
        self.bank_journal.checkbook_id = False
```

4. En `test_action_post_on_disabled_journal`, reemplazar la aserción final por:

```python
        self.assertEqual(self.checkbook.next_number, '00001001')
```

5. En `test_other_payment_method_is_out_of_scope`, reemplazar

```python
        self.assertFalse(payment._check_sequence_journal())
        payment.action_post()
        self.assertEqual(self.bank_journal.next_check_number, '00001001')
```

por

```python
        self.assertFalse(payment._check_sequence_checkbook())
        payment.action_post()
        self.assertEqual(self.checkbook.next_number, '00001001')
```

6. `Command` y `fields` ya no se usan en este archivo: verificar que no queden imports sin usar.

- [ ] **Paso 3: Escribir los tests del comportamiento compartido**

En `account_journal_check_sequence/tests/test_checkbook.py`, reemplazar el bloque de imports del encabezado por:

```python
from psycopg2 import IntegrityError

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import CheckbookTestCommon
```

Después, agregar al final del archivo:

```python
@tagged('post_install', '-at_install')
class TestCheckbookSharing(CheckbookTestCommon):
    """Varios diarios, de una o varias compañías, sobre la misma chequera."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal_b = cls._create_bank_journal('Banco Sucursal B', 'BSUB', checkbook=cls.checkbook)
        cls.own_checks_line_b = cls._setup_own_checks_line(cls.journal_b, cls.outstanding_account)

    def test_shared_checkbook_continues_across_journals(self):
        """Lo que publica un diario lo ve el otro: sugiere el número siguiente."""
        payment_a = self._create_own_check_payment([
            {'payment_date': self.check_date, 'amount': 10},
        ])
        payment_a.action_post()
        self.assertEqual(payment_a.l10n_latam_new_check_ids.name, '00001001')

        payment_b = self._create_own_check_payment(
            [{'payment_date': self.check_date, 'amount': 20}],
            journal=self.journal_b, own_checks_line=self.own_checks_line_b,
        )
        self.assertEqual(payment_b.l10n_latam_new_check_ids.name, '00001002')

    def test_shared_journals_computed(self):
        """El diario informa qué otros diarios comparten su chequera."""
        self.assertEqual(self.bank_journal.checkbook_shared_journal_ids, self.journal_b)
        self.assertEqual(self.journal_b.checkbook_shared_journal_ids, self.bank_journal)

    def test_edit_next_number_from_journal_updates_checkbook(self):
        """Editar el número desde un diario cambia la chequera de todos."""
        self.journal_b.next_check_number = '00002000'
        self.assertEqual(self.checkbook.next_number, '00002000')
        self.assertEqual(self.bank_journal.next_check_number, '00002000')

    def test_enabled_follows_checkbook(self):
        """La numeración está activa si el diario tiene una chequera activa."""
        self.assertTrue(self.bank_journal.check_sequence_enabled)
        self.checkbook.active = False
        self.assertFalse(self.bank_journal.check_sequence_enabled)

    def test_archived_checkbook_disables_numbering(self):
        """Con la chequera archivada no se sugiere número ni avanza al publicar."""
        self.checkbook.active = False
        payment = self._create_own_check_payment([
            {'payment_date': self.check_date, 'amount': 10},
        ])
        self.assertFalse(payment.l10n_latam_new_check_ids.name)
        payment.l10n_latam_new_check_ids.name = '00005000'
        payment.action_post()
        self.assertEqual(self.checkbook.next_number, '00001001')

    def test_cannot_delete_checkbook_in_use(self):
        """Una chequera asignada a un diario no se puede borrar, solo archivar."""
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
            self.checkbook.unlink()

    def test_checkbook_company_must_match_journal(self):
        """Una chequera de otra compañía no se puede asignar al diario."""
        company_2 = self.setup_other_company()['company']
        # sudo: la compañía 2 no está activa y la regla impediría crearla.
        foreign_checkbook = self.env['account.checkbook'].sudo().create({
            'name': 'Chequera Compañía 2',
            'company_id': company_2.id,
        })
        with self.assertRaises(ValidationError):
            self.bank_journal.sudo().checkbook_id = foreign_checkbook

    def test_checkbook_company_change_checks_journals(self):
        """Cambiarle la compañía a una chequera en uso valida sus diarios."""
        company_2 = self.setup_other_company()['company']
        with self.assertRaises(ValidationError):
            self.checkbook.company_id = company_2


@tagged('post_install', '-at_install')
class TestCheckbookMultiCompany(CheckbookTestCommon):
    """Una chequera sin compañía compartida por diarios de dos compañías."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_second_company()
        cls.journal_c2 = cls.env['account.journal'].browse(cls.company_data_2['default_journal_bank'].id)
        cls.journal_c2.checkbook_id = cls.checkbook
        cls.own_checks_line_c2 = cls._setup_own_checks_line(cls.journal_c2, cls.outstanding_account_2)

    def test_counter_advances_from_both_companies(self):
        """Publicar desde cada compañía avanza el mismo contador."""
        payment_1 = self._create_own_check_payment([
            {'payment_date': self.check_date, 'amount': 10},
        ])
        payment_1.action_post()
        payment_2 = self._create_own_check_payment(
            [{'payment_date': self.check_date, 'amount': 20}],
            journal=self.journal_c2, own_checks_line=self.own_checks_line_c2,
        )
        self.assertEqual(payment_2.l10n_latam_new_check_ids.name, '00001002')
        payment_2.action_post()
        self.assertEqual(self.checkbook.next_number, '00001003')
```

- [ ] **Paso 4: Correr los tests y verificar que fallan**

Correr los tests.
Esperado: FALLA. `account.journal` no tiene el campo `checkbook_id` (error en el `setUpClass` de `CheckbookTestCommon`).

- [ ] **Paso 5: Reescribir `account_journal.py`**

Reemplazar todo el contenido de `account_journal_check_sequence/models/account_journal.py` por:

```python
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    checkbook_id = fields.Many2one(
        'account.checkbook',
        string='Chequera',
        ondelete='restrict',
        copy=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Chequera de la que salen los cheques propios de este diario. Varios diarios '
             'pueden compartir la misma chequera y consumen un único correlativo. Sin '
             'chequera, el módulo no numera los cheques de este diario.',
    )
    # La numeración está activa cuando hay chequera: el booleano ya no es una
    # fuente de verdad propia, se mantiene para no romper referencias externas.
    check_sequence_enabled = fields.Boolean(
        string='Auto-numerar Cheques Propios',
        compute='_compute_check_sequence_enabled',
        help='Campo técnico: el diario tiene asignada una chequera activa.',
    )
    # Se editan desde el diario pero viven en la chequera: si la comparten
    # varios diarios, el cambio aplica a todos.
    next_check_number = fields.Char(
        related='checkbook_id.next_number',
        readonly=False,
    )
    check_number_padding = fields.Integer(
        related='checkbook_id.padding',
        readonly=False,
    )
    checkbook_shared_journal_ids = fields.Many2many(
        'account.journal',
        string='Otros Diarios de la Chequera',
        compute='_compute_checkbook_shared_journal_ids',
    )

    @api.depends('checkbook_id.active')
    def _compute_check_sequence_enabled(self):
        for journal in self:
            journal.check_sequence_enabled = bool(journal.checkbook_id.active)

    @api.depends('checkbook_id.journal_ids')
    def _compute_checkbook_shared_journal_ids(self):
        for journal in self:
            journal.checkbook_shared_journal_ids = journal.checkbook_id.journal_ids - journal._origin

    @api.constrains('checkbook_id', 'company_id')
    def _check_checkbook_company(self):
        for journal in self:
            checkbook_company = journal.checkbook_id.company_id
            if checkbook_company and checkbook_company != journal.company_id:
                raise ValidationError(_(
                    'La chequera "%(checkbook)s" es de la compañía %(checkbook_company)s y no se '
                    'puede usar en el diario "%(journal)s" de %(journal_company)s. Para compartirla '
                    'entre compañías, dejá vacía la compañía de la chequera.',
                    checkbook=journal.checkbook_id.display_name,
                    checkbook_company=checkbook_company.display_name,
                    journal=journal.display_name,
                    journal_company=journal.company_id.display_name,
                ))
```

- [ ] **Paso 6: Agregar `journal_ids` y la validación de compañía en la chequera**

En `account_journal_check_sequence/models/account_checkbook.py`, agregar después del campo `company_id`:

```python
    journal_ids = fields.One2many(
        'account.journal',
        'checkbook_id',
        string='Diarios',
        readonly=True,
        help='Diarios de banco que numeran sus cheques propios con esta chequera.',
    )
```

Y después de `_check_padding`:

```python
    @api.constrains('company_id')
    def _check_company_journals(self):
        # sudo: los diarios de compañías no activas también tienen que coincidir.
        self.sudo().journal_ids._check_checkbook_company()
```

- [ ] **Paso 7: Pasar los mixins a la chequera**

En `account_journal_check_sequence/models/account_check_sequence_mixin.py`, reemplazar `_check_sequence_journal`, el compute y `_apply_check_sequence_suggestion` por:

```python
    def _check_sequence_checkbook(self):
        """Chequera activa del diario si el registro emite cheques propios; si no, vacío."""
        self.ensure_one()
        checkbook = self.journal_id.checkbook_id
        if checkbook.active and self._is_own_check_payment():
            return checkbook
        return self.env['account.checkbook']

    def _get_check_numbers_used(self):
        """Números de cheque efectivamente cargados en el registro."""
        self.ensure_one()
        return [check.name for check in self.l10n_latam_new_check_ids if check.name]

    @api.depends(
        'journal_id.checkbook_id.active', 'journal_id.checkbook_id.next_number',
        'payment_method_line_id', 'l10n_latam_new_check_ids.name',
    )
    def _compute_check_sequence_next_number(self):
        for rec in self:
            checkbook = rec._check_sequence_checkbook()
            if not checkbook:
                rec.check_sequence_next_number = False
                continue
            used_numbers = rec._get_check_numbers_used()
            start_from = checkbook._get_highest_check_number(used_numbers) if used_numbers else False
            rec.check_sequence_next_number = checkbook._peek_check_numbers(1, start_from=start_from)[0]

    def _apply_check_sequence_suggestion(self):
        """Completa los números de cheque faltantes con el correlativo de la chequera.

        Las líneas tipeadas por el usuario son anclas fijas: se respetan tal
        cual y el resto encadena a partir de ellas. Una línea es del usuario
        cuando tiene número y ese número ya no coincide con
        ``autofilled_check_number``, es decir apenas la edita.

        Todo lo demás (vacío o autocompletado por el módulo) se recalcula en
        cada pasada. Por eso una línea autocompletada sigue al salto que el
        usuario haga más arriba: si cambia la primera de 00001001 a 00001050
        porque arrancó otra chequera, la siguiente pasa a 00001051. Y por eso
        se corrige sola si quedó repitiendo el número de otra.
        """
        for rec in self:
            checkbook = rec._check_sequence_checkbook()
            if not checkbook:
                continue
            used_numbers = []
            for check in rec.l10n_latam_new_check_ids:
                is_autofilled = check.name and check.name == check.autofilled_check_number
                if check.name and not is_autofilled:
                    used_numbers.append(check.name)
                    continue
                start_from = checkbook._get_highest_check_number(used_numbers) if used_numbers else False
                check.name = checkbook._peek_check_numbers(1, start_from=start_from)[0]
                check.autofilled_check_number = check.name
                used_numbers.append(check.name)
```

(`_get_check_numbers_used` no cambia: se incluye solo para ubicar el bloque.)

En `account_journal_check_sequence/models/account_check_sequence_line_mixin.py`, reemplazar `_get_next_check_number_for_line` por:

```python
    @api.model
    def _get_next_check_number_for_line(self, parent, extra_used=None):
        """Próximo número libre considerando las líneas ya cargadas en el padre."""
        checkbook = parent._check_sequence_checkbook()
        if not checkbook:
            return False
        used_numbers = parent._get_check_numbers_used() + list(extra_used or [])
        start_from = checkbook._get_highest_check_number(used_numbers) if used_numbers else False
        return checkbook._peek_check_numbers(1, start_from=start_from)[0]
```

Y en el docstring de `default_get` de ese archivo, cambiar "El contador del diario no sirve por sí solo" por "El contador de la chequera no sirve por sí solo".

- [ ] **Paso 8: Pasar la publicación a la chequera**

En `account_journal_check_sequence/models/account_payment.py`, reemplazar `action_post` por:

```python
    def action_post(self):
        """Actualiza el contador de la chequera con el número más alto emitido."""
        res = super().action_post()
        for payment in self:
            checkbook = payment._check_sequence_checkbook()
            if not checkbook:
                continue
            used_numbers = payment._get_check_numbers_used()
            if used_numbers:
                checkbook._increment_check_number(checkbook._get_highest_check_number(used_numbers))
        return res
```

- [ ] **Paso 9: Verificar que no queden referencias viejas**

```bash
grep -rn "_check_sequence_journal\|journal._increment\|journal._peek\|check_sequence_enabled = \|FOR UPDATE" account_journal_check_sequence --include=*.py
```

Esperado: ninguna coincidencia fuera de docstrings.

- [ ] **Paso 10: Verificación local**

Correr `compileall` y la validación de XML.
Esperado: `PY_OK` y `XML_OK`.

- [ ] **Paso 11: Correr los tests y verificar que pasan**

Correr los tests.
Esperado: PASA, con todo `test_check_sequence.py`, `TestCheckbookCounter`, `TestCheckbookSharing` y `TestCheckbookMultiCompany` en verde.

Si `TestCheckbookMultiCompany` falla al crear el pago en la compañía 2 por falta de cuenta a pagar del partner, en su `setUpClass` hay que asignar `partner_a.with_company(company_2).property_account_payable_id = cls.company_data_2['default_account_payable']`.

La vista del diario todavía referencia los campos viejos, pero los campos se siguen llamando igual (ahora son related), así que la actualización del módulo no falla.

- [ ] **Paso 12: Commit**

```bash
git add account_journal_check_sequence/models account_journal_check_sequence/tests
git commit -m "feat(account_journal_check_sequence): el diario numera desde una chequera compartible" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 3: Chequera emisora en el cheque y control de duplicados

**Archivos:**
- Modificar: `account_journal_check_sequence/models/l10n_latam_check.py`
- Modificar: `account_journal_check_sequence/models/account_payment.py`
- Crear: `account_journal_check_sequence/tests/test_check_duplicates.py`
- Modificar: `account_journal_check_sequence/tests/test_check_sequence.py` (docstring de un test)
- Modificar: `account_journal_check_sequence/tests/__init__.py`

- [ ] **Paso 1: Escribir los tests**

Crear `account_journal_check_sequence/tests/test_check_duplicates.py`:

```python
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import CheckbookTestCommon


@tagged('post_install', '-at_install')
class TestCheckDuplicates(CheckbookTestCommon):
    """Un número ya emitido en la chequera no se puede volver a usar."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal_b = cls._create_bank_journal('Banco Sucursal B', 'BSUB', checkbook=cls.checkbook)
        cls.own_checks_line_b = cls._setup_own_checks_line(cls.journal_b, cls.outstanding_account)

    def _post_check(self, number, journal=None, own_checks_line=None):
        payment = self._create_own_check_payment(
            [{'name': number, 'payment_date': self.check_date, 'amount': 10}],
            journal=journal, own_checks_line=own_checks_line,
        )
        payment.action_post()
        return payment

    def _draft_check_in_b(self, number):
        return self._create_own_check_payment(
            [{'name': number, 'payment_date': self.check_date, 'amount': 10}],
            journal=self.journal_b, own_checks_line=self.own_checks_line_b,
        )

    def test_post_sets_checkbook_on_checks(self):
        """Al publicar, cada cheque queda asociado a la chequera que lo emitió."""
        payment = self._post_check('00001050')
        self.assertEqual(payment.l10n_latam_new_check_ids.checkbook_id, self.checkbook)

    def test_duplicate_across_journals_warns_and_blocks(self):
        """El mismo número desde otro diario de la chequera avisa y bloquea."""
        self._post_check('00001050')
        payment_b = self._draft_check_in_b('00001050')
        self.assertIn('00001050', payment_b.l10n_latam_check_warning_msg or '')
        self.assertIn('Chequera Test', payment_b.l10n_latam_check_warning_msg)
        with self.assertRaises(ValidationError):
            payment_b.action_post()

    def test_duplicate_within_payment_blocks(self):
        """El mismo número dos veces en un pago también bloquea."""
        payment = self._create_own_check_payment([
            {'name': '00001050', 'payment_date': self.check_date, 'amount': 10},
            {'name': '00001050', 'payment_date': self.check_date, 'amount': 20},
        ])
        self.assertIn('más de una vez', payment.l10n_latam_check_warning_msg or '')
        with self.assertRaises(ValidationError):
            payment.action_post()

    def test_canceled_payment_does_not_block(self):
        """Un número de un pago cancelado queda libre."""
        payment = self._post_check('00001050')
        payment.action_cancel()
        payment_b = self._draft_check_in_b('00001050')
        payment_b.action_post()
        self.assertEqual(payment_b.state, 'in_process')

    def test_draft_payment_does_not_block(self):
        """Un número cargado en un borrador todavía no está emitido."""
        self._create_own_check_payment([
            {'name': '00001050', 'payment_date': self.check_date, 'amount': 10},
        ])
        payment_b = self._draft_check_in_b('00001050')
        self.assertFalse(payment_b.l10n_latam_check_warning_msg)
        payment_b.action_post()

    def test_voided_check_blocks(self):
        """Un cheque anulado igual ocupó su número."""
        payment = self._post_check('00001050')
        payment.l10n_latam_new_check_ids.action_void()
        with self.assertRaises(ValidationError):
            self._draft_check_in_b('00001050').action_post()

    def test_other_checkbook_does_not_block(self):
        """El mismo número en otra chequera no es un duplicado."""
        other = self.env['account.checkbook'].create({'name': 'Otra', 'next_number': '00000001'})
        journal_c = self._create_bank_journal('Banco C', 'BNCC', checkbook=other)
        line_c = self._setup_own_checks_line(journal_c, self.outstanding_account)
        self._post_check('00001050')
        self._post_check('00001050', journal=journal_c, own_checks_line=line_c)

    def test_previous_checkbook_of_journal_does_not_block(self):
        """Los cheques emitidos con la chequera anterior de un diario no cuentan."""
        other = self.env['account.checkbook'].create({'name': 'Anterior', 'next_number': '00000001'})
        self.journal_b.checkbook_id = other
        self._post_check('00001050', journal=self.journal_b, own_checks_line=self.own_checks_line_b)
        self.journal_b.checkbook_id = self.checkbook
        self._post_check('00001050')

    def test_journal_without_checkbook_skips_control(self):
        """Sin chequera, el módulo no controla (queda solo el índice nativo)."""
        journal_c = self._create_bank_journal('Banco C', 'BNCC')
        line_c = self._setup_own_checks_line(journal_c, self.outstanding_account)
        self._post_check('00001050')
        self._post_check('00001050', journal=journal_c, own_checks_line=line_c)
```

Modificar `account_journal_check_sequence/tests/__init__.py`:

```python
from . import test_check_duplicates
from . import test_check_sequence
from . import test_checkbook
```

En `test_check_sequence.py`, dentro de `test_suggestion_respects_user_typed_duplicate`, reemplazar la oración del docstring

```
        el índice único de l10n_latam.check se lo va a marcar al publicar: es
        preferible eso a cambiarle en silencio un número que escribió a mano.
```

por

```
        el control de duplicados de la chequera se lo marca en el formulario y
        bloquea la publicación: es preferible eso a cambiarle en silencio un
        número que escribió a mano.
```

- [ ] **Paso 2: Correr los tests y verificar que fallan**

Correr los tests.
Esperado: FALLA. `l10n_latam.check` no tiene `checkbook_id`, y los tests de duplicados entre diarios no lanzan `ValidationError`.

Si `test_canceled_payment_does_not_block` falla por el estado: el estado de un pago de cheque propio publicado en v19 puede ser `in_process` o `paid`. En ese caso, cambiar la aserción a `assertNotIn(payment_b.state, ('draft', 'canceled'))`.

- [ ] **Paso 3: Agregar `checkbook_id` al cheque**

En `account_journal_check_sequence/models/l10n_latam_check.py`, cambiar el import a `from odoo import api, fields, models` y agregar después de `_check_sequence_parent_field`:

```python
    checkbook_id = fields.Many2one(
        'account.checkbook',
        string='Chequera',
        readonly=True,
        copy=False,
        index=True,
        help='Chequera de la que se emitió el cheque. Se completa al publicar el pago y '
             'se usa para detectar números repetidos entre diarios que comparten chequera.',
    )
```

- [ ] **Paso 4: Lock antes de publicar, chequera en los cheques y control de duplicados**

En `account_journal_check_sequence/models/account_payment.py`:
- Cambiar el import a `from odoo import _, api, models`.
- Reemplazar `action_post` por el bloque de abajo.
- Agregar los dos métodos nuevos.

```python
    def action_post(self):
        """Publica serializando por chequera y avanza el contador.

        El lock de las chequeras se toma antes de ``super()`` porque ahí adentro
        corre el control de números duplicados (ver
        ``_get_blocking_l10n_latam_warning_msg``). Si se tomara después, dos
        pagos concurrentes con el mismo número pasarían el control los dos.
        """
        checkbooks = self.env['account.checkbook']
        for payment in self:
            checkbooks |= payment._check_sequence_checkbook()
        checkbooks._lock_checkbooks()
        res = super().action_post()
        for payment in self:
            checkbook = payment._check_sequence_checkbook()
            if not checkbook:
                continue
            payment.l10n_latam_new_check_ids.write({'checkbook_id': checkbook.id})
            used_numbers = payment._get_check_numbers_used()
            if used_numbers:
                checkbook._increment_check_number(checkbook._get_highest_check_number(used_numbers))
        return res

    def _get_blocking_l10n_latam_warning_msg(self):
        """Suma los números de cheque ya usados en la chequera.

        El método nativo alimenta la alerta del formulario
        (``l10n_latam_check_warning_msg``) y el ``ValidationError`` de
        ``action_post``, así que con esto se cubren las dos cosas. El índice
        único nativo es por línea de método de pago, es decir por diario: no
        ve duplicados entre diarios que comparten chequera.
        """
        msgs = super()._get_blocking_l10n_latam_warning_msg()
        for rec in self.filtered(lambda payment: payment.state == 'draft'):
            msgs.extend(rec._get_checkbook_duplicate_msgs())
        return msgs

    def _get_checkbook_duplicate_msgs(self):
        """Mensajes por cada número repetido en el pago o ya emitido en la chequera.

        Cuenta todo cheque de la chequera cuyo pago no esté en borrador ni
        cancelado, incluidos los anulados: ese número ya se usó en papel. Se
        busca con ``sudo()`` porque la chequera puede estar compartida entre
        compañías y los cheques de otra compañía no son visibles para el
        usuario, pero igual ocupan el número.
        """
        self.ensure_one()
        checkbook = self._check_sequence_checkbook()
        names = self._get_check_numbers_used()
        if not checkbook or not names:
            return []
        msgs = [
            _('El cheque %(number)s está cargado más de una vez en este pago.', number=name)
            for name in sorted({name for name in names if names.count(name) > 1})
        ]
        used_checks = self.env['l10n_latam.check'].sudo().search([
            ('checkbook_id', '=', checkbook.id),
            ('name', 'in', list(set(names))),
            ('payment_id.state', 'not in', ('draft', 'canceled')),
            ('id', 'not in', self.l10n_latam_new_check_ids._origin.ids),
        ], order='name, id')
        for check in used_checks:
            msgs.append(_(
                'El cheque %(number)s de la chequera «%(checkbook)s» ya fue emitido en '
                '%(payment)s (diario %(journal)s).',
                number=check.name,
                checkbook=checkbook.name,
                payment=check.payment_id.display_name,
                journal=check.payment_id.journal_id.display_name,
            ))
        return msgs
```

- [ ] **Paso 5: Verificación local**

Correr `compileall`.
Esperado: `PY_OK`.

- [ ] **Paso 6: Correr los tests y verificar que pasan**

Correr los tests.
Esperado: PASA, con `TestCheckDuplicates` completo y el resto de las suites en verde.

- [ ] **Paso 7: Commit**

```bash
git add account_journal_check_sequence/models account_journal_check_sequence/tests
git commit -m "feat(account_journal_check_sequence): bloquear números de cheque ya emitidos en la chequera" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 4: Vistas y menú

**Archivos:**
- Crear: `account_journal_check_sequence/views/account_checkbook_views.xml`
- Modificar: `account_journal_check_sequence/views/account_journal_views.xml`
- Modificar: `account_journal_check_sequence/__manifest__.py` (`data`)

- [ ] **Paso 1: Crear las vistas de la chequera**

Crear `account_journal_check_sequence/views/account_checkbook_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_account_checkbook_list" model="ir.ui.view">
        <field name="name">account.checkbook.list</field>
        <field name="model">account.checkbook</field>
        <field name="arch" type="xml">
            <list string="Chequeras">
                <field name="name"/>
                <field name="next_number"/>
                <field name="padding"/>
                <field name="company_id" groups="base.group_multi_company"/>
                <field name="journal_ids" widget="many2many_tags"/>
            </list>
        </field>
    </record>

    <record id="view_account_checkbook_form" model="ir.ui.view">
        <field name="name">account.checkbook.form</field>
        <field name="model">account.checkbook</field>
        <field name="arch" type="xml">
            <form string="Chequera">
                <sheet>
                    <widget name="web_ribbon" title="Archivada" bg_color="text-bg-danger" invisible="active"/>
                    <field name="active" invisible="1"/>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1><field name="name" placeholder="Ej. Galicia – Serie B"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="next_number"/>
                            <field name="padding"/>
                        </group>
                        <group>
                            <field name="company_id" groups="base.group_multi_company"
                                   placeholder="Compartida entre compañías"/>
                        </group>
                    </group>
                    <separator string="Diarios que usan esta chequera"/>
                    <field name="journal_ids" readonly="1">
                        <list>
                            <field name="name"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </list>
                    </field>
                </sheet>
            </form>
        </field>
    </record>

    <record id="view_account_checkbook_search" model="ir.ui.view">
        <field name="name">account.checkbook.search</field>
        <field name="model">account.checkbook</field>
        <field name="arch" type="xml">
            <search string="Chequeras">
                <field name="name"/>
                <field name="journal_ids"/>
                <filter name="without_journals" string="Sin diarios" domain="[('journal_ids', '=', False)]"/>
                <separator/>
                <filter name="inactive" string="Archivadas" domain="[('active', '=', False)]"/>
            </search>
        </field>
    </record>

    <record id="action_account_checkbook" model="ir.actions.act_window">
        <field name="name">Chequeras</field>
        <field name="res_model">account.checkbook</field>
        <field name="view_mode">list,form</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Creá una chequera</p>
            <p>
                Una chequera lleva el correlativo de los cheques propios. Asignala a uno o
                varios diarios de banco para que compartan la numeración.
            </p>
        </field>
    </record>

    <menuitem id="menu_account_checkbook"
              action="action_account_checkbook"
              parent="account.account_account_menu"
              sequence="4"
              groups="account.group_account_manager"/>
</odoo>
```

- [ ] **Paso 2: Reemplazar el grupo del diario**

En `account_journal_check_sequence/views/account_journal_views.xml`, reemplazar el `<group name="check_sequence" ...>` completo por:

```xml
                <group name="check_sequence" string="Chequera / Numeración de Cheques Propios"
                       invisible="type != 'bank'">
                    <field name="checkbook_id" context="{'default_company_id': company_id}"/>
                    <field name="next_check_number" invisible="not checkbook_id"/>
                    <field name="check_number_padding" invisible="not checkbook_id"/>
                    <div class="alert alert-info" role="alert" colspan="2"
                         invisible="not checkbook_shared_journal_ids">
                        Esta chequera también la usan:
                        <field name="checkbook_shared_journal_ids" widget="many2many_tags" readonly="1" class="d-inline"/>
                        Si cambiás el próximo número, el cambio aplica a todos.
                    </div>
                </group>
```

- [ ] **Paso 3: Registrar la vista en el manifiesto**

En `account_journal_check_sequence/__manifest__.py`, dejar `data` así:

```python
    'data': [
        'security/ir.model.access.csv',
        'security/account_checkbook_security.xml',
        'views/account_checkbook_views.xml',
        'views/account_journal_views.xml',
        'views/account_payment_views.xml',
    ],
```

- [ ] **Paso 4: Verificación local**

Correr la validación de XML y el script de RNG.
Esperado: `XML_OK` y `RNG_OK`. La lista y la búsqueda nuevas validan contra `list_view.rng` y `search_view.rng`. La búsqueda no usa `<group string=...>`, que en v19 es inválido.

- [ ] **Paso 5: Actualizar el módulo y revisar la UI**

Correr los tests. Esto también actualiza el módulo, así que un error de vistas aparece como `ParseError`.
Esperado: PASA sin `ParseError`.

Si hay instancia, revisar manualmente:
- Contabilidad → Configuración → Contabilidad → Chequeras.
- En un diario de banco, la creación rápida de una chequera.
- El aviso que aparece cuando dos diarios comparten chequera.

- [ ] **Paso 6: Commit**

```bash
git add account_journal_check_sequence/views account_journal_check_sequence/__manifest__.py
git commit -m "feat(account_journal_check_sequence): vistas y menú de chequeras" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 5: Migración 19.0.1.3.0

**Archivos:**
- Crear: `account_journal_check_sequence/migrations/19.0.1.3.0/post-migrate.py`
- Modificar: `account_journal_check_sequence/__manifest__.py` (`version`)
- Crear: `account_journal_check_sequence/tests/test_migration.py`
- Modificar: `account_journal_check_sequence/tests/__init__.py`

La carpeta `migrations/19.0.1.0.0` tiene un `__init__.py`. Odoo no lo necesita, pero para seguir la convención del repo se crea uno vacío también en la carpeta nueva.

- [ ] **Paso 1: Escribir el test**

Crear `account_journal_check_sequence/tests/test_migration.py`:

```python
import importlib.util

from odoo.tests import tagged
from odoo.tools.misc import file_path

from .common import CheckbookTestCommon


def _load_migrate():
    """Carga ``migrate`` del script (el nombre de carpeta no es importable)."""
    path = file_path('account_journal_check_sequence/migrations/19.0.1.3.0/post-migrate.py')
    spec = importlib.util.spec_from_file_location('check_sequence_migrate_19_0_1_3_0', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.migrate


@tagged('post_install', '-at_install')
class TestMigration(CheckbookTestCommon):

    def _add_legacy_columns(self):
        """Recrea las columnas que la versión 19.0.1.2.0 dejaba en account_journal.

        En una base actualizada existen (Odoo no borra columnas); en la base de
        tests, instalada de cero, no. El DDL se deshace con la transacción del test.
        """
        self.env.cr.execute("""
            ALTER TABLE account_journal
                ADD COLUMN IF NOT EXISTS check_sequence_enabled boolean,
                ADD COLUMN IF NOT EXISTS next_check_number varchar,
                ADD COLUMN IF NOT EXISTS check_number_padding integer
        """)

    def test_migration_creates_checkbook_and_backfills_checks(self):
        # Diario que en 19.0.1.2.0 numeraba por su cuenta y ya emitió un cheque.
        legacy_journal = self._create_bank_journal('Banco Legado', 'BLEG')
        legacy_line = self._setup_own_checks_line(legacy_journal, self.outstanding_account)
        legacy_payment = self._create_own_check_payment(
            [{'name': '00000700', 'payment_date': self.check_date, 'amount': 10}],
            journal=legacy_journal, own_checks_line=legacy_line,
        )
        legacy_payment.action_post()
        self.env.flush_all()
        self._add_legacy_columns()
        self.env.cr.execute("""
            UPDATE account_journal
               SET check_sequence_enabled = TRUE,
                   next_check_number = ' 00000701 ',
                   check_number_padding = 99
             WHERE id = %s
        """, (legacy_journal.id,))

        migrate = _load_migrate()
        migrate(self.env.cr, '19.0.1.2.0')
        self.env.invalidate_all()

        checkbook = legacy_journal.checkbook_id
        self.assertTrue(checkbook)
        self.assertEqual(checkbook.name, 'Banco Legado')
        self.assertEqual(checkbook.next_number, '00000701')
        self.assertEqual(checkbook.padding, 8, 'Un padding fuera de rango vuelve al default.')
        self.assertEqual(checkbook.company_id, legacy_journal.company_id)
        self.assertEqual(legacy_payment.l10n_latam_new_check_ids.checkbook_id, checkbook)

        checkbook_count = self.env['account.checkbook'].with_context(active_test=False).search_count([])
        migrate(self.env.cr, '19.0.1.2.0')
        self.assertEqual(
            self.env['account.checkbook'].with_context(active_test=False).search_count([]),
            checkbook_count,
            'La migración es idempotente.',
        )

    def test_migration_skips_fresh_install(self):
        """Sin versión previa no hace nada."""
        checkbook_count = self.env['account.checkbook'].search_count([])
        _load_migrate()(self.env.cr, None)
        self.assertEqual(self.env['account.checkbook'].search_count([]), checkbook_count)
```

Agregar `from . import test_migration` a `tests/__init__.py`, en orden alfabético.

- [ ] **Paso 2: Correr los tests y verificar que fallan**

Correr los tests.
Esperado: FALLA. `file_path` no encuentra `migrations/19.0.1.3.0/post-migrate.py` (`FileNotFoundError`).

- [ ] **Paso 3: Escribir el script**

Crear `account_journal_check_sequence/migrations/19.0.1.3.0/__init__.py` vacío y `account_journal_check_sequence/migrations/19.0.1.3.0/post-migrate.py`:

```python
import logging

from odoo import SUPERUSER_ID, api
from odoo.addons.account_journal_check_sequence.models.account_checkbook import (
    DEFAULT_CHECK_NUMBER_PADDING,
    MAX_CHECK_NUMBER_PADDING,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migración 19.0.1.2.0 → 19.0.1.3.0

    El contador de cheques pasa del diario a la chequera (``account.checkbook``):

    1. Por cada diario de banco con la numeración activa y sin chequera, se
       crea una chequera con su próximo número, su padding y su compañía, y se
       le asigna. No se fusiona nada: no hay forma de saber qué diarios
       comparten chequera física. Eso se hace después con el asistente
       "Unificar chequeras".
    2. Se completa la chequera emisora en los cheques propios ya emitidos,
       para que el control de números duplicados cubra la historia.

    Las columnas viejas de ``account_journal`` quedan como respaldo. El
    script es idempotente: solo toca diarios y cheques sin chequera.
    """
    if not version:
        return
    cr.execute("""
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'account_journal'
           AND column_name = 'check_sequence_enabled'
    """)
    if not cr.fetchone():
        return

    # ORM para crear las chequeras: account.journal.name es jsonb traducible.
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("""
        SELECT id, next_check_number, check_number_padding
          FROM account_journal
         WHERE check_sequence_enabled IS TRUE
           AND type = 'bank'
           AND checkbook_id IS NULL
         ORDER BY id
    """)
    rows = cr.fetchall()
    for journal_id, next_number, padding in rows:
        journal = env['account.journal'].browse(journal_id)
        valid_padding = padding and 1 <= padding <= MAX_CHECK_NUMBER_PADDING
        journal.checkbook_id = env['account.checkbook'].create({
            'name': journal.name,
            'next_number': (next_number or '').strip() or '00000001',
            'padding': padding if valid_padding else DEFAULT_CHECK_NUMBER_PADDING,
            'company_id': journal.company_id.id,
        })
    if rows:
        _logger.info('post-migrate: %s chequera(s) creada(s) a partir de los diarios', len(rows))
    env.flush_all()

    cr.execute("""
        UPDATE l10n_latam_check AS chk
           SET checkbook_id = journal.checkbook_id
          FROM account_payment AS payment
          JOIN account_journal AS journal ON journal.id = payment.journal_id
          JOIN account_payment_method_line AS method_line ON method_line.id = payment.payment_method_line_id
          JOIN account_payment_method AS method ON method.id = method_line.payment_method_id
         WHERE chk.payment_id = payment.id
           AND chk.checkbook_id IS NULL
           AND chk.outstanding_line_id IS NOT NULL
           AND method.code = 'own_checks'
           AND journal.checkbook_id IS NOT NULL
    """)
    if cr.rowcount:
        _logger.info('post-migrate: chequera completada en %s cheque(s) propio(s) ya emitido(s)', cr.rowcount)
```

En `account_journal_check_sequence/__manifest__.py`, cambiar `'version': '19.0.1.2.0'` por `'version': '19.0.1.3.0'`.

- [ ] **Paso 4: Verificación local**

Correr `compileall`.
Esperado: `PY_OK`.

- [ ] **Paso 5: Correr los tests y verificar que pasan**

Correr los tests.
Esperado: PASA con `TestMigration`.

Si hay una copia de una base de un cliente en 19.0.1.2.0, probar también `-u account_journal_check_sequence` sobre ella y revisar en el log las líneas `post-migrate: ...`.

- [ ] **Paso 6: Commit**

```bash
git add account_journal_check_sequence/migrations/19.0.1.3.0 account_journal_check_sequence/__manifest__.py account_journal_check_sequence/tests
git commit -m "feat(account_journal_check_sequence): migración de diarios a chequeras" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 6: Asistente "Unificar chequeras"

**Archivos:**
- Crear: `account_journal_check_sequence/wizards/account_checkbook_merge.py`
- Crear: `account_journal_check_sequence/wizards/account_checkbook_merge_views.xml`
- Modificar: `account_journal_check_sequence/wizards/__init__.py`
- Modificar: `account_journal_check_sequence/security/ir.model.access.csv`
- Modificar: `account_journal_check_sequence/__manifest__.py` (`data`)
- Crear: `account_journal_check_sequence/tests/test_checkbook_merge.py`
- Modificar: `account_journal_check_sequence/tests/__init__.py`

- [ ] **Paso 1: Escribir los tests**

Crear `account_journal_check_sequence/tests/test_checkbook_merge.py`:

```python
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CheckbookTestCommon


@tagged('post_install', '-at_install')
class TestCheckbookMerge(CheckbookTestCommon):
    """Unificar chequeras de sucursales que comparten la chequera física."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_second_company()
        company_2 = cls.company_2

        # Sucursal B: misma compañía, chequera propia creada por la migración.
        cls.checkbook_b = cls.env['account.checkbook'].create({
            'name': 'Chequera B', 'next_number': '00001040',
            'company_id': cls.company_data['company'].id,
        })
        cls.journal_b = cls._create_bank_journal('Banco Sucursal B', 'BSUB', checkbook=cls.checkbook_b)
        cls.own_checks_line_b = cls._setup_own_checks_line(cls.journal_b, cls.outstanding_account)

        # Sucursal C: otra compañía.
        cls.checkbook_c = cls.env['account.checkbook'].create({
            'name': 'Chequera C', 'next_number': '00001020', 'company_id': company_2.id,
        })
        cls.journal_c = cls.env['account.journal'].browse(cls.company_data_2['default_journal_bank'].id)
        cls.journal_c.checkbook_id = cls.checkbook_c

    def _merge_wizard(self, checkbooks, **vals):
        return self.env['account.checkbook.merge'].with_context(
            active_model='account.checkbook', active_ids=checkbooks.ids,
        ).create(vals)

    def test_defaults(self):
        """Propone el número más alto y deja la compañía vacía si hay varias."""
        wizard = self._merge_wizard(self.checkbook | self.checkbook_b | self.checkbook_c)
        self.assertEqual(wizard.checkbook_ids, self.checkbook | self.checkbook_b | self.checkbook_c)
        self.assertEqual(wizard.next_number, '00001040')
        self.assertFalse(wizard.company_id)
        self.assertIn(wizard.target_checkbook_id, wizard.checkbook_ids)

    def test_merge_moves_journals_and_archives_sources(self):
        """Todos los diarios quedan en la destino, sin compañía; el resto se archiva."""
        wizard = self._merge_wizard(
            self.checkbook | self.checkbook_b | self.checkbook_c,
            target_checkbook_id=self.checkbook.id,
        )
        wizard.action_merge()
        self.assertEqual(self.journal_b.checkbook_id, self.checkbook)
        self.assertEqual(self.journal_c.checkbook_id, self.checkbook)
        self.assertFalse(self.checkbook.company_id)
        self.assertEqual(self.checkbook.next_number, '00001040')
        self.assertFalse(self.checkbook_b.active)
        self.assertFalse(self.checkbook_c.active)

    def test_merge_moves_issued_checks(self):
        """Los cheques emitidos pasan a la destino y el control de duplicados los ve."""
        payment_b = self._create_own_check_payment(
            [{'name': '00001040', 'payment_date': self.check_date, 'amount': 10}],
            journal=self.journal_b, own_checks_line=self.own_checks_line_b,
        )
        payment_b.action_post()
        self._merge_wizard(
            self.checkbook | self.checkbook_b, target_checkbook_id=self.checkbook.id,
        ).action_merge()
        self.assertEqual(payment_b.l10n_latam_new_check_ids.checkbook_id, self.checkbook)
        payment_a = self._create_own_check_payment([
            {'name': '00001040', 'payment_date': self.check_date, 'amount': 10},
        ])
        with self.assertRaises(ValidationError):
            payment_a.action_post()

    def test_edited_next_number_is_respected(self):
        """El próximo número elegido por el usuario se respeta aunque sea menor."""
        self._merge_wizard(
            self.checkbook | self.checkbook_b,
            target_checkbook_id=self.checkbook.id,
            next_number='00000900',
        ).action_merge()
        self.assertEqual(self.checkbook.next_number, '00000900')

    def test_same_company_keeps_company(self):
        """Si todos los diarios son de la misma compañía, la destino la conserva."""
        wizard = self._merge_wizard(self.checkbook | self.checkbook_b, target_checkbook_id=self.checkbook_b.id)
        self.assertEqual(wizard.company_id, self.company_data['company'])
        wizard.action_merge()
        self.assertEqual(self.checkbook_b.company_id, self.company_data['company'])
        self.assertEqual(self.bank_journal.checkbook_id, self.checkbook_b)

    def test_duplicate_warning_does_not_block(self):
        """Los números ya repetidos entre las chequeras se informan pero no impiden unificar."""
        for journal, line in ((self.bank_journal, self.own_checks_line), (self.journal_b, self.own_checks_line_b)):
            self._create_own_check_payment(
                [{'name': '00000777', 'payment_date': self.check_date, 'amount': 10}],
                journal=journal, own_checks_line=line,
            ).action_post()
        wizard = self._merge_wizard(self.checkbook | self.checkbook_b, target_checkbook_id=self.checkbook.id)
        self.assertIn('00000777', wizard.duplicate_warning or '')
        wizard.action_merge()
        self.assertEqual(self.journal_b.checkbook_id, self.checkbook)

    def test_no_duplicate_warning_without_repeats(self):
        wizard = self._merge_wizard(self.checkbook | self.checkbook_b, target_checkbook_id=self.checkbook.id)
        self.assertFalse(wizard.duplicate_warning)

    def test_requires_two_checkbooks(self):
        with self.assertRaises(UserError):
            self._merge_wizard(self.checkbook, target_checkbook_id=self.checkbook.id).action_merge()

    def test_target_must_be_selected(self):
        with self.assertRaises(UserError):
            self._merge_wizard(
                self.checkbook | self.checkbook_b, target_checkbook_id=self.checkbook_c.id,
            ).action_merge()
```

Agregar `from . import test_checkbook_merge` a `tests/__init__.py`, en orden alfabético.

- [ ] **Paso 2: Correr los tests y verificar que fallan**

Correr los tests.
Esperado: FALLA. `KeyError: 'account.checkbook.merge'`.

- [ ] **Paso 3: Crear el asistente**

Crear `account_journal_check_sequence/wizards/account_checkbook_merge.py`:

```python
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Cantidad de números repetidos que se listan en el aviso del asistente.
MAX_DUPLICATES_SHOWN = 20


class AccountCheckbookMerge(models.TransientModel):
    """Unifica chequeras de diarios que emiten de la misma chequera física.

    La migración crea una chequera por diario; con este asistente se agrupan.
    Además de reasignar los diarios, mueve los cheques ya emitidos a la
    chequera destino: si no, el control de duplicados no vería los números
    que emitió cada sucursal antes de unificar.
    """

    _name = 'account.checkbook.merge'
    _description = 'Unificar chequeras'

    checkbook_ids = fields.Many2many(
        'account.checkbook',
        string='Chequeras',
        required=True,
        default=lambda self: self._default_checkbook_ids(),
    )
    target_checkbook_id = fields.Many2one(
        'account.checkbook',
        string='Chequera destino',
        required=True,
        compute='_compute_target_checkbook_id',
        store=True,
        readonly=False,
        domain="[('id', 'in', checkbook_ids)]",
    )
    next_number = fields.Char(
        string='Próximo Número de Cheque',
        required=True,
        compute='_compute_next_number',
        store=True,
        readonly=False,
        help='Por defecto, el más alto de las chequeras seleccionadas. Se respeta aunque '
             'sea menor que el actual.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía resultante',
        compute='_compute_merge_scope',
        help='Compañía que queda en la chequera destino. Vacía si los diarios son de '
             'más de una compañía: la chequera queda compartida entre compañías.',
    )
    journal_ids = fields.Many2many(
        'account.journal',
        string='Diarios',
        compute='_compute_merge_scope',
        help='Diarios que van a quedar en la chequera destino (de las compañías activas).',
    )
    duplicate_warning = fields.Text(compute='_compute_duplicate_warning')

    @api.model
    def _default_checkbook_ids(self):
        if self.env.context.get('active_model') != 'account.checkbook':
            return self.env['account.checkbook']
        return self.env['account.checkbook'].browse(self.env.context.get('active_ids', []))

    @api.model
    def _get_all_journals(self, checkbooks):
        """Diarios de las chequeras, incluidos los de compañías no activas y los archivados."""
        return self.env['account.journal'].sudo().with_context(active_test=False).search([
            ('checkbook_id', 'in', checkbooks.ids),
        ])

    @api.depends('checkbook_ids')
    def _compute_target_checkbook_id(self):
        for wizard in self:
            checkbooks = wizard.checkbook_ids._origin
            if wizard.target_checkbook_id._origin in checkbooks:
                continue
            journals = self._get_all_journals(checkbooks)
            # La que más diarios tiene: es la que menos cambios implica.
            wizard.target_checkbook_id = checkbooks.sorted(
                lambda checkbook: (-len(journals.filtered(lambda j: j.checkbook_id == checkbook)), checkbook.id)
            )[:1]

    @api.depends('checkbook_ids')
    def _compute_next_number(self):
        for wizard in self:
            checkbooks = wizard.checkbook_ids._origin
            numbers = [number for number in checkbooks.mapped('next_number') if number]
            wizard.next_number = checkbooks[:1]._get_highest_check_number(numbers) if numbers else False

    @api.depends('checkbook_ids')
    def _compute_merge_scope(self):
        for wizard in self:
            checkbooks = wizard.checkbook_ids._origin
            companies = self._get_all_journals(checkbooks).company_id
            wizard.company_id = companies.id if len(companies) == 1 else False
            wizard.journal_ids = self.env['account.journal'].search([('checkbook_id', 'in', checkbooks.ids)])

    @api.depends('checkbook_ids')
    def _compute_duplicate_warning(self):
        # sudo: la chequera puede tener cheques emitidos desde otras compañías.
        checks = self.env['l10n_latam.check'].sudo()
        for wizard in self:
            domain = [
                ('checkbook_id', 'in', wizard.checkbook_ids._origin.ids),
                ('payment_id.state', 'not in', ('draft', 'canceled')),
            ]
            groups = checks._read_group(domain, ['name'], ['__count'], having=[('__count', '>', 1)], order='name')
            if not groups:
                wizard.duplicate_warning = False
                continue
            names = [name for name, _count in groups]
            lines = []
            for name in names[:MAX_DUPLICATES_SHOWN]:
                payments = checks.search(domain + [('name', '=', name)]).payment_id
                lines.append(f"{name}: {', '.join(payments.mapped('display_name'))}")
            if len(names) > MAX_DUPLICATES_SHOWN:
                lines.append(_('… y %(count)s números más.', count=len(names) - MAX_DUPLICATES_SHOWN))
            wizard.duplicate_warning = '\n'.join([
                _('Hay números de cheque repetidos entre los ya emitidos. La unificación no los '
                  'corrige, pero conviene revisarlos:'),
                *lines,
            ])

    def action_merge(self):
        self.ensure_one()
        checkbooks = self.checkbook_ids
        target = self.target_checkbook_id
        if len(checkbooks) < 2:
            raise UserError(_('Seleccioná al menos dos chequeras para unificar.'))
        if target not in checkbooks:
            raise UserError(_('La chequera destino tiene que estar entre las seleccionadas.'))
        sources = checkbooks - target

        # Ningún pago puede publicar contra estas chequeras mientras se mueven.
        checkbooks._lock_checkbooks()
        # Primero la compañía: si no, la constraint rechaza los diarios nuevos.
        target.company_id = self.company_id
        self._get_all_journals(sources).write({'checkbook_id': target.id})
        self.env['l10n_latam.check'].sudo().search([
            ('checkbook_id', 'in', sources.ids),
        ]).write({'checkbook_id': target.id})
        # Decisión explícita del usuario: no aplica la regla de "no retroceder".
        target.next_number = self.next_number
        sources.active = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.checkbook',
            'res_id': target.id,
            'view_mode': 'form',
            'target': 'current',
        }
```

El aviso agrupa por número entre **todas** las chequeras seleccionadas, así que un número emitido en la chequera A y también en la B aparece antes de unificar. Es justamente el caso de dos sucursales que numeraban en paralelo.

Modificar `account_journal_check_sequence/wizards/__init__.py`:

```python
from . import account_checkbook_merge
from . import account_payment_register
```

- [ ] **Paso 4: Crear la vista y la acción**

Crear `account_journal_check_sequence/wizards/account_checkbook_merge_views.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_account_checkbook_merge_form" model="ir.ui.view">
        <field name="name">account.checkbook.merge.form</field>
        <field name="model">account.checkbook.merge</field>
        <field name="arch" type="xml">
            <form string="Unificar chequeras">
                <div class="alert alert-warning" role="alert" invisible="not duplicate_warning">
                    <field name="duplicate_warning" nolabel="1"/>
                </div>
                <p class="text-muted">
                    Los diarios y los cheques ya emitidos de las chequeras seleccionadas pasan a
                    la chequera destino. Las demás quedan archivadas.
                </p>
                <group>
                    <field name="checkbook_ids" widget="many2many_tags"/>
                    <field name="target_checkbook_id" options="{'no_create': True}"/>
                    <field name="next_number"/>
                    <field name="company_id" groups="base.group_multi_company"
                           placeholder="Compartida entre compañías"/>
                    <field name="journal_ids" widget="many2many_tags"/>
                </group>
                <footer>
                    <button name="action_merge" type="object" string="Unificar" class="btn-primary" data-hotkey="q"/>
                    <button string="Cancelar" special="cancel" class="btn-secondary" data-hotkey="x"/>
                </footer>
            </form>
        </field>
    </record>

    <record id="action_account_checkbook_merge" model="ir.actions.act_window">
        <field name="name">Unificar chequeras</field>
        <field name="res_model">account.checkbook.merge</field>
        <field name="view_mode">form</field>
        <field name="view_id" ref="view_account_checkbook_merge_form"/>
        <field name="target">new</field>
        <field name="binding_model_id" ref="model_account_checkbook"/>
        <field name="binding_type">action</field>
        <field name="binding_view_types">list</field>
        <field name="group_ids" eval="[(6, 0, [ref('account.group_account_manager')])]"/>
    </record>
</odoo>
```

- [ ] **Paso 5: Registrar acceso y datos**

Agregar al final de `account_journal_check_sequence/security/ir.model.access.csv`:

```csv
access_account_checkbook_merge_manager,account.checkbook.merge.manager,model_account_checkbook_merge,account.group_account_manager,1,1,1,1
```

En `account_journal_check_sequence/__manifest__.py`, dejar `data` así:

```python
    'data': [
        'security/ir.model.access.csv',
        'security/account_checkbook_security.xml',
        'views/account_checkbook_views.xml',
        'views/account_journal_views.xml',
        'views/account_payment_views.xml',
        'wizards/account_checkbook_merge_views.xml',
    ],
```

- [ ] **Paso 6: Verificación local**

Correr `compileall`, la validación de XML y el script de RNG.
Esperado: `PY_OK`, `XML_OK` y `RNG_OK`.

- [ ] **Paso 7: Correr los tests y verificar que pasan**

Correr los tests.
Esperado: PASA con `TestCheckbookMerge` y el resto de las suites en verde.

Si `test_merge_moves_journals_and_archives_sources` falla al leer `self.journal_c` por reglas de compañía, ya usa `sudo()`. Revisar que el test no lea otros campos del diario sin `sudo()`.

- [ ] **Paso 8: Commit**

```bash
git add account_journal_check_sequence/wizards account_journal_check_sequence/security account_journal_check_sequence/__manifest__.py account_journal_check_sequence/tests
git commit -m "feat(account_journal_check_sequence): asistente para unificar chequeras" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 7: Manifiesto, README y spec

**Archivos:**
- Modificar: `account_journal_check_sequence/__manifest__.py` (`name`, `summary`, `description`)
- Modificar: `account_journal_check_sequence/README.md`
- Modificar: `docs/superpowers/specs/2026-09-23-shared-checkbook-design.md` (ubicación del menú)

- [ ] **Paso 1: Manifiesto**

En `account_journal_check_sequence/__manifest__.py`, reemplazar `summary` y `description` por:

```python
    'summary': 'Chequeras de cheques propios compartibles entre diarios de banco y compañías.',
    'description': """
        Chequeras de Cheques Propios (Odoo 19 / ADHOC)
        ==============================================
        * Numeración secuencial ("tipo chequera") en un modelo propio, account.checkbook.
        * Varios diarios de banco, incluso de distintas compañías, pueden compartir la misma chequera y siguen un único correlativo.
        * Sugiere automáticamente el próximo número de cheque al registrar pagos (compatible con Órdenes de Pago de ADHOC y pagos estándar).
        * Permite al usuario editar libremente el número de cheque si necesita saltear números.
        * Actualiza automáticamente el contador al confirmar/publicar el pago, sin permitir que retroceda.
        * Bloquea números de cheque ya emitidos en la misma chequera, sin importar el diario o la compañía.
        * Asistente para unificar las chequeras de diarios que emiten de la misma chequera física.
        * Alcance: método de pago "Cheque Propio" (own_checks) de l10n_latam_check.
        * Serializa los pagos publicados en paralelo sobre la misma chequera.
    """,
```

El `name` queda igual: es el nombre con el que el cliente conoce el módulo.

- [ ] **Paso 2: README**

En `account_journal_check_sequence/README.md`:

1. En el párrafo de introducción, reemplazar "a nivel de cada diario de banco" por "en chequeras que pueden compartir varios diarios de banco, incluso de distintas compañías".

2. Reemplazar el punto **1. Configuración por Diario de Banco** de "Funcionalidades Principales" por:

```markdown
1. **Chequeras (`account.checkbook`):**
   * Cada chequera tiene su **Próximo Número de Cheque** (`next_number`, admite prefijo y sufijo, ej. `E-00000100`) y sus **Dígitos del Cheque** (`padding`, por defecto 8; admite de 1 a 20).
   * Un diario de banco numera sus cheques propios si tiene una chequera asignada (`checkbook_id`). **Varios diarios pueden compartir la misma chequera** y siguen un único correlativo.
   * Si la chequera no tiene compañía, la pueden usar diarios de **distintas compañías**. Si tiene compañía, solo diarios de esa compañía.
   * Desde el diario se sigue viendo y editando el próximo número y los dígitos, pero el cambio se guarda en la chequera: si la comparten varios diarios, aplica a todos. El formulario del diario avisa qué otros diarios la usan.
   * Una chequera **archivada** deja de sugerir números y no avanza al publicar. Una chequera en uso no se puede borrar.
```

3. En el punto **3**, reemplazar el bullet "Un número duplicado **tipeado por el usuario** no se reescribe: si fue un error, lo marca el índice único de `l10n_latam.check` al publicar..." por:

```markdown
   * Un número duplicado **tipeado por el usuario** no se reescribe: si fue un error, lo marca el control de duplicados (ver punto 5). Es preferible eso a cambiarle en silencio un valor que escribió a mano.
```

4. En el punto **4**, reemplazar las menciones de "diario" por "chequera". Reemplazar además el último bullet, el del lock, por:

```markdown
   * Antes de publicar se toma un lock exclusivo sobre la chequera (un `UPDATE` que no cambia el valor). Dos pagos publicados en paralelo sobre la misma chequera, aunque sean de diarios o compañías distintos, se serializan: el segundo espera y, cuando el primero confirma, Odoo lo reintenta y ya ve el número emitido. Se usa sin `NOWAIT` a propósito, para que el segundo pago espere en lugar de fallar.
```

5. Agregar después del punto 4:

```markdown
5. **Control de Números Duplicados:**
   * Al publicar, cada cheque guarda la chequera que lo emitió (`l10n_latam.check.checkbook_id`).
   * Si un número ya fue emitido en la misma chequera, desde cualquier diario o compañía, el pago muestra el aviso rojo de cheques mientras se carga y **no deja publicar**. Lo mismo si el número se repite dentro del mismo pago.
   * Cuentan los cheques de pagos publicados, incluidos los anulados (ese número ya se usó en papel). No cuentan los pagos en borrador ni los cancelados.
   * Odoo trae de fábrica un índice único, pero es por diario: no detecta duplicados entre diarios que comparten chequera.

6. **Asistente "Unificar chequeras":**
   * Desde la lista de chequeras, seleccionar varias y usar la acción **Unificar chequeras**.
   * Propone como destino la chequera con más diarios y como próximo número el más alto de todas; los dos se pueden cambiar.
   * Pasa a la chequera destino todos los diarios **y los cheques ya emitidos**, y archiva las demás. Si los diarios son de más de una compañía, la destino queda sin compañía.
   * Informa los números que ya estaban repetidos en la historia; no los corrige ni impide unificar.
```

6. Reemplazar la sección **⚙️ Configuración** por:

```markdown
## ⚙️ Configuración

1. Ir a **Contabilidad > Configuración > Contabilidad > Chequeras** y crear una chequera con el número del próximo cheque físico/electrónico a emitir (ej. `00001001`). Si la van a usar diarios de varias compañías, dejar la compañía vacía.
2. En cada diario de banco que emite de esa chequera (**Configuración Avanzada > Chequera / Numeración de Cheques Propios**), elegir la chequera. También se puede crear desde ahí escribiendo el nombre.
3. Guardar.

### Puesta en marcha después de actualizar desde 19.0.1.2.0

La actualización crea una chequera por cada diario que tenía la numeración activa, con su número actual. Si varias sucursales emiten de la misma chequera física:

1. Ir a **Chequeras**, seleccionar las chequeras de esas sucursales y usar **Unificar chequeras**.
2. Revisar el próximo número propuesto y el aviso de números repetidos, si aparece.
3. Confirmar.
```

7. Agregar a la sección **🚚 Migración** un apartado:

```markdown
### 19.0.1.2.0 → 19.0.1.3.0

`migrations/19.0.1.3.0/post-migrate.py`:

1. Crea una chequera por cada diario de banco con la numeración activa y le copia el próximo número, los dígitos y la compañía.
2. Completa la chequera emisora en los cheques propios ya emitidos, para que el control de duplicados cubra la historia.

No fusiona chequeras (para eso está el asistente) y deja en `account_journal` las columnas viejas como respaldo. Es idempotente.
```

- [ ] **Paso 3: Corregir la ubicación del menú en la spec**

En `docs/superpowers/specs/2026-09-23-shared-checkbook-design.md`, reemplazar

```
  - Acción y menú: Contabilidad → Configuración → Bancos → **Chequeras**,
    visible solo para `account.group_account_manager`.
```

por

```
  - Acción y menú: Contabilidad → Configuración → Contabilidad →
    **Chequeras** (`account.account_account_menu`, al lado de Diarios; en
    v19 no hay submenú "Bancos"), visible solo para
    `account.group_account_manager`.
```

- [ ] **Paso 4: Verificación final**

```bash
python -m compileall -q account_journal_check_sequence && echo PY_OK
```

Correr también la validación de XML y el script de RNG, y la suite completa de tests.
Esperado: `PY_OK`, `XML_OK`, `RNG_OK` y todas las suites en verde:
- `TestCheckSequence`
- `TestCheckbookCounter`
- `TestCheckbookSharing`
- `TestCheckbookMultiCompany`
- `TestCheckDuplicates`
- `TestMigration`
- `TestCheckbookMerge`

```bash
grep -rn "check_sequence_journal\|por diario de banco" account_journal_check_sequence
```

Esperado: ninguna coincidencia.

- [ ] **Paso 5: Commit**

```bash
git add account_journal_check_sequence/__manifest__.py account_journal_check_sequence/README.md docs/superpowers/specs/2026-09-23-shared-checkbook-design.md
git commit -m "docs(account_journal_check_sequence): documentar chequeras compartidas y unificación" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
