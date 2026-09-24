# Importador de Listas de Proveedores — Plan de implementación

> **Para agentes:** implementar tarea por tarea, en orden. Cada paso usa checkbox (`- [ ]`).
> Si usás superpowers: REQUIRED SUB-SKILL `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`.

**Goal:** Crear `alpardata_supplier_pricelist_import`: importar listas de precios de
proveedores (Excel/CSV o aumento porcentual), revisar el impacto en una vista previa y
aplicarlas con fecha de vigencia creando nuevas fichas `product.supplierinfo`.

**Architecture:** Tres modelos persistentes (perfil de mapeo, importación, línea). La
lectura de archivos vive en funciones puras (`tools/readers.py`); el cálculo de
reposición reutiliza `compute_replacement_cost` del punto 1; la aplicación crea
supplierinfos y deja que el módulo base cierre vigencias y registre historial.

**Tech Stack:** Odoo 19.0, `openpyxl` (incluido en los requirements de Odoo), `csv`.

**Spec:** `docs/superpowers/specs/2026-09-24-supplier-pricelist-import-design.md`
**Requisito previo:** punto 1 (`alpardata_purchase_replacement_cost`) mergeado en `19.0`.

---

## Convenciones

- **Rama:** `feat/supplier-pricelist-import` desde `19.0` (con el punto 1 ya mergeado).
- Strings y commits en castellano. Commits `feat(supplier_pricelist_import): ...`.
- **Odoo 19:** `<list>`, `invisible="expr"`, `<chatter/>`, `<search>` sin
  `<group string>`, `res.groups` con `group_ids`, `product.supplierinfo.product_uom_id`.
- Fuente de Odoo: `C:\Users\Santiago\Desktop\Odoo\odoo-19.0`.
- **Tests:**

  ```bash
  odoo-bin -c odoo.conf -d odoo19_dev -u alpardata_supplier_pricelist_import --test-enable --test-tags /alpardata_supplier_pricelist_import --stop-after-init --log-level=test
  ```

  Sin instancia: `python -m py_compile` y parseo de XML con lxml; commit con
  `[tests no ejecutados]`.

## Mapa de archivos (todo nuevo, bajo `alpardata_supplier_pricelist_import/`)

- `__init__.py`, `__manifest__.py`, `README.md`
- `tools/__init__.py`, `tools/readers.py` — lectura xlsx/csv, normalización
- `models/__init__.py`
- `models/supplier_pricelist_import_profile.py`
- `models/supplier_pricelist_import.py` — importación: preview y aplicación
- `models/supplier_pricelist_import_line.py`
- `models/res_partner.py` — smart button
- `data/ir_sequence.xml`
- `security/security.xml`, `security/ir.model.access.csv`
- `views/supplier_pricelist_import_profile_views.xml`,
  `views/supplier_pricelist_import_views.xml`, `views/res_partner_views.xml`,
  `views/menus.xml`
- `tests/__init__.py`, `tests/common.py`, `tests/test_readers.py`,
  `tests/test_preview.py`, `tests/test_apply.py`

---

### Tarea 1: Esqueleto y lectores de archivo

**Files:** Create `__init__.py`, `__manifest__.py`, `tools/__init__.py`, `tools/readers.py`,
`models/__init__.py`, `tests/__init__.py`, `tests/test_readers.py`.

- [ ] **Paso 1: `__init__.py`**

```python
from . import models
```

- [ ] **Paso 2: `__manifest__.py`**

```python
{
    'name': 'AlparData - Importador de Listas de Proveedores',
    'version': '19.0.1.0.0',
    'summary': 'Importa listas de precios de proveedores (Excel/CSV o % de aumento) con vista previa y fecha de vigencia',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Inventory/Purchase',
    'depends': ['alpardata_purchase_replacement_cost'],
    'external_dependencies': {'python': ['openpyxl']},
    'data': [],  # la tarea 5 agrega seguridad, datos y vistas
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

- [ ] **Paso 3: `models/__init__.py`** (todo comentado; cada tarea descomenta lo suyo)

```python
# from . import supplier_pricelist_import_profile
# from . import supplier_pricelist_import_line
# from . import supplier_pricelist_import
# from . import res_partner
```

- [ ] **Paso 4: `tests/__init__.py`**

```python
from . import test_readers
# from . import test_preview
# from . import test_apply
```

- [ ] **Paso 5: test que falla** — `tests/test_readers.py`

```python
from __future__ import annotations

import io

import openpyxl

from odoo.tests import tagged
from odoo.tests.common import BaseCase

from odoo.addons.alpardata_supplier_pricelist_import.tools.readers import (
    normalize_header,
    parse_number,
    read_csv,
    read_xlsx,
)


def make_xlsx(rows, sheet='Lista', leading_rows=0):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for _ in range(leading_rows):
        ws.append(['Lista de precios Proveedor SA'])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@tagged('post_install', '-at_install')
class TestReaders(BaseCase):

    def test_normalize_header(self):
        self.assertEqual(normalize_header('  Código  Artículo '), 'codigo articulo')
        self.assertEqual(normalize_header('PRECIO'), 'precio')
        self.assertEqual(normalize_header(None), '')

    def test_parse_number(self):
        self.assertEqual(parse_number(12.5, ','), 12.5)
        self.assertEqual(parse_number('1.234,50', ','), 1234.5)
        self.assertEqual(parse_number('1,234.50', '.'), 1234.5)
        self.assertEqual(parse_number('$ 99,9', ','), 99.9)
        self.assertIsNone(parse_number('abc', ','))
        self.assertIsNone(parse_number('', ','))
        self.assertIsNone(parse_number(None, ','))

    def test_read_xlsx_with_header_row(self):
        content = make_xlsx(
            [['Código', 'Descripción', 'Precio'], ['A1', 'Coca', 100], ['A2', 'Fanta', '90,5']],
            leading_rows=2,
        )
        rows = read_xlsx(content, sheet_name='Lista', header_row=3)
        self.assertEqual(rows[0], (4, {'codigo': 'A1', 'descripcion': 'Coca', 'precio': 100}))
        self.assertEqual(rows[1][0], 5)
        self.assertEqual(rows[1][1]['precio'], '90,5')

    def test_read_xlsx_missing_sheet(self):
        content = make_xlsx([['Código', 'Precio']])
        with self.assertRaises(ValueError):
            read_xlsx(content, sheet_name='Otra', header_row=1)

    def test_read_xlsx_first_sheet_by_default(self):
        content = make_xlsx([['Código', 'Precio'], ['A1', 10]])
        rows = read_xlsx(content, sheet_name=False, header_row=1)
        self.assertEqual(rows, [(2, {'codigo': 'A1', 'precio': 10})])

    def test_read_csv_latin1(self):
        content = 'Código;Precio\nA1;1.234,50\n\nA2;10\n'.encode('latin-1')
        rows = read_csv(content, delimiter=';', encoding='latin-1', header_row=1)
        self.assertEqual(rows, [
            (2, {'codigo': 'A1', 'precio': '1.234,50'}),
            (4, {'codigo': 'A2', 'precio': '10'}),
        ])
```

- [ ] **Paso 6: correr** → falla (no existe `tools.readers`).

- [ ] **Paso 7: `tools/__init__.py`** — vacío (un archivo con una línea de comentario):

```python
# Funciones puras de lectura de archivos de listas de proveedores.
```

- [ ] **Paso 8: `tools/readers.py`**

```python
"""Lectura de listas de precios de proveedores (xlsx / csv).

Funciones puras: devuelven [(numero_de_fila, {encabezado_normalizado: valor})],
salteando filas vacías. Los encabezados se normalizan para comparar contra el
perfil sin importar mayúsculas, acentos ni espacios.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata

import openpyxl

Row = tuple[int, dict[str, object]]


def normalize_header(value) -> str:
    if value is None:
        return ''
    text = unicodedata.normalize('NFKD', str(value))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', text).strip().lower()


def parse_number(value, decimal: str) -> float | None:
    """Convierte un valor de planilla a float. `decimal` es ',' o '.'.

    Números nativos se devuelven tal cual. Texto: se quitan símbolos de moneda
    y espacios, se elimina el separador de miles y se normaliza el decimal.
    Devuelve None si no es un número.
    """
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r'[^\d,.\-]', '', str(value))
    if not text:
        return None
    thousands = '.' if decimal == ',' else ','
    text = text.replace(thousands, '').replace(decimal, '.')
    try:
        return float(text)
    except ValueError:
        return None


def _rows_from_matrix(matrix, header_row: int) -> list[Row]:
    if len(matrix) < header_row:
        raise ValueError(f'El archivo tiene menos de {header_row} filas.')
    headers = [normalize_header(h) for h in matrix[header_row - 1]]
    rows: list[Row] = []
    for offset, raw in enumerate(matrix[header_row:], start=header_row + 1):
        if not any(cell not in (None, '') for cell in raw):
            continue
        rows.append((offset, {
            header: raw[idx] if idx < len(raw) else None
            for idx, header in enumerate(headers) if header
        }))
    return rows


def read_xlsx(content: bytes, sheet_name: str | bool, header_row: int) -> list[Row]:
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(
                f'La hoja "{sheet_name}" no existe. Hojas: {", ".join(workbook.sheetnames)}.'
            )
        sheet = workbook[sheet_name]
    else:
        sheet = workbook.worksheets[0]
    matrix = [list(row) for row in sheet.iter_rows(values_only=True)]
    return _rows_from_matrix(matrix, header_row)


def read_csv(content: bytes, delimiter: str, encoding: str, header_row: int) -> list[Row]:
    text = content.decode(encoding)
    matrix = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    # csv.reader devuelve [] para líneas vacías: se mantienen para no correr la numeración
    matrix = [row if row else [] for row in matrix]
    return _rows_from_matrix(matrix, header_row)
```

- [ ] **Paso 9: correr** → `TestReaders` pasa.

- [ ] **Paso 10: commit**

```bash
git add alpardata_supplier_pricelist_import
git commit -m "feat(supplier_pricelist_import): esqueleto y lectores de xlsx/csv"
```

---

### Tarea 2: Modelos (perfil, importación, línea)

**Files:** Create `models/supplier_pricelist_import_profile.py`,
`models/supplier_pricelist_import_line.py`, `models/supplier_pricelist_import.py`
(sólo campos y estados; la lógica va en tareas 3 y 4), `data/ir_sequence.xml`.

- [ ] **Paso 1: `models/supplier_pricelist_import_profile.py`**

```python
from __future__ import annotations

from odoo import fields, models


class SupplierPricelistImportProfile(models.Model):
    _name = 'supplier.pricelist.import.profile'
    _description = 'Perfil de importación de lista de proveedor'
    _order = 'partner_id, name'
    _check_company_auto = True

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )
    file_type = fields.Selection(
        [('xlsx', 'Excel (.xlsx)'), ('csv', 'CSV')],
        string='Tipo de archivo', required=True, default='xlsx',
    )
    sheet_name = fields.Char(string='Hoja', help='Vacío: primera hoja.')
    header_row = fields.Integer(string='Fila de encabezados', default=1, required=True)
    csv_delimiter = fields.Char(string='Separador CSV', size=1, default=';')
    csv_decimal = fields.Selection(
        [(',', 'Coma'), ('.', 'Punto')], string='Separador decimal', default=',', required=True,
    )
    csv_encoding = fields.Selection(
        [('utf-8', 'UTF-8'), ('latin-1', 'Latin-1 (Windows)')],
        string='Codificación CSV', default='utf-8',
    )
    match_by = fields.Selection(
        [
            ('supplier_code', 'Código del proveedor'),
            ('barcode', 'Código de barras'),
            ('default_code', 'Referencia interna'),
        ],
        string='Buscar producto por', required=True, default='supplier_code',
    )
    col_code = fields.Char(string='Columna código', required=True)
    col_price = fields.Char(string='Columna precio', required=True)
    col_cascade = fields.Char(string='Columna bonificaciones', help='Opcional.')
    price_includes_vat = fields.Boolean(string='El precio incluye IVA')
    vat_pct = fields.Float(string='IVA (%)', default=21.0)

    _header_row_positive = models.Constraint(
        'CHECK(header_row >= 1)', 'La fila de encabezados debe ser 1 o mayor.',
    )
```

> Odoo 19 declara restricciones SQL con `models.Constraint` (no `_sql_constraints`),
> como en `odoo-19.0/addons/product/models/product_tag.py`.

- [ ] **Paso 2: `models/supplier_pricelist_import_line.py`**

```python
from __future__ import annotations

from odoo import fields, models


class SupplierPricelistImportLine(models.Model):
    _name = 'supplier.pricelist.import.line'
    _description = 'Línea de importación de lista de proveedor'
    _order = 'import_id, row_number, id'

    import_id = fields.Many2one(
        'supplier.pricelist.import', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='import_id.company_id', store=True)
    row_number = fields.Integer(string='Fila')
    code = fields.Char(string='Código')
    supplierinfo_id = fields.Many2one('product.supplierinfo', string='Ficha de proveedor')
    product_tmpl_id = fields.Many2one('product.template', string='Producto')
    old_list_price = fields.Float(string='Lista anterior', digits='Product Price')
    new_list_price = fields.Float(string='Lista nueva', digits='Product Price')
    variation_pct = fields.Float(string='Variación (%)', digits=(16, 2))
    old_cascade = fields.Char(string='Bonif. anterior')
    new_cascade = fields.Char(string='Bonif. nueva')
    old_replacement_cost = fields.Float(string='Reposición anterior', digits='Product Price')
    new_replacement_cost = fields.Float(string='Reposición nueva', digits='Product Price')
    status = fields.Selection(
        [
            ('change', 'Cambia'),
            ('unchanged', 'Sin cambio'),
            ('not_found', 'No encontrado'),
            ('error', 'Error'),
        ],
        string='Estado', required=True, index=True,
    )
    message = fields.Char(string='Mensaje')
    to_apply = fields.Boolean(string='Aplicar')
```

- [ ] **Paso 3: `models/supplier_pricelist_import.py`** (campos; la tarea 3 agrega métodos)

```python
from __future__ import annotations

import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class SupplierPricelistImport(models.Model):
    _name = 'supplier.pricelist.import'
    _description = 'Importación de lista de proveedor'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(string='Número', readonly=True, copy=False, default='/')
    partner_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True, tracking=True, index=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )
    mode = fields.Selection(
        [('file', 'Archivo del proveedor'), ('percent', 'Aumento porcentual')],
        string='Modo', required=True, default='file',
    )
    profile_id = fields.Many2one(
        'supplier.pricelist.import.profile', string='Perfil',
        domain="[('partner_id', '=', partner_id)]", check_company=True,
    )
    file = fields.Binary(string='Archivo', attachment=True)
    file_name = fields.Char(string='Nombre del archivo')
    percent = fields.Float(string='Variación (%)', help='Negativo para bajas.')
    filter_categ_ids = fields.Many2many(
        'product.category', string='Categorías', help='Incluye subcategorías.',
    )
    filter_tag_ids = fields.Many2many('product.tag', string='Etiquetas')
    effective_date = fields.Date(
        string='Vigente desde', required=True, default=fields.Date.context_today, tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('preview', 'Vista previa'),
            ('done', 'Aplicada'),
            ('cancelled', 'Cancelada'),
        ],
        string='Estado', default='draft', required=True, tracking=True, copy=False,
    )
    line_ids = fields.One2many('supplier.pricelist.import.line', 'import_id', string='Líneas')
    applied_date = fields.Datetime(string='Aplicada el', readonly=True, copy=False)
    applied_by = fields.Many2one('res.users', string='Aplicada por', readonly=True, copy=False)
    count_change = fields.Integer(compute='_compute_counts', string='Cambian')
    count_unchanged = fields.Integer(compute='_compute_counts', string='Sin cambio')
    count_not_found = fields.Integer(compute='_compute_counts', string='No encontrados')
    count_error = fields.Integer(compute='_compute_counts', string='Errores')

    @api.depends('line_ids.status')
    def _compute_counts(self) -> None:
        for rec in self:
            statuses = rec.line_ids.mapped('status')
            rec.count_change = statuses.count('change')
            rec.count_unchanged = statuses.count('unchanged')
            rec.count_not_found = statuses.count('not_found')
            rec.count_error = statuses.count('error')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'supplier.pricelist.import'
                ) or '/'
        return super().create(vals_list)
```

- [ ] **Paso 4: `data/ir_sequence.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="seq_supplier_pricelist_import" model="ir.sequence">
        <field name="name">Importación de listas de proveedores</field>
        <field name="code">supplier.pricelist.import</field>
        <field name="prefix">IMPL/%(year)s/</field>
        <field name="padding">4</field>
        <field name="company_id" eval="False"/>
    </record>
</odoo>
```

- [ ] **Paso 5: `security/ir.model.access.csv`** (necesario para que los modelos carguen sin
warnings; los grupos se explican en el spec)

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_spl_profile_user,supplier.pricelist.import.profile.user,model_supplier_pricelist_import_profile,purchase.group_purchase_user,1,0,0,0
access_spl_profile_manager,supplier.pricelist.import.profile.manager,model_supplier_pricelist_import_profile,purchase.group_purchase_manager,1,1,1,1
access_spl_import_user,supplier.pricelist.import.user,model_supplier_pricelist_import,purchase.group_purchase_user,1,1,1,0
access_spl_import_manager,supplier.pricelist.import.manager,model_supplier_pricelist_import,purchase.group_purchase_manager,1,1,1,1
access_spl_line_user,supplier.pricelist.import.line.user,model_supplier_pricelist_import_line,purchase.group_purchase_user,1,1,1,1
```

- [ ] **Paso 6: `security/security.xml`** (record rules multi-company)

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="rule_spl_profile_company" model="ir.rule">
        <field name="name">Perfil de lista de proveedor: multi-empresa</field>
        <field name="model_id" ref="model_supplier_pricelist_import_profile"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    </record>
    <record id="rule_spl_import_company" model="ir.rule">
        <field name="name">Importación de lista de proveedor: multi-empresa</field>
        <field name="model_id" ref="model_supplier_pricelist_import"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    </record>
    <record id="rule_spl_line_company" model="ir.rule">
        <field name="name">Línea de importación: multi-empresa</field>
        <field name="model_id" ref="model_supplier_pricelist_import_line"/>
        <field name="global" eval="True"/>
        <field name="domain_force">[('company_id', 'in', company_ids)]</field>
    </record>
</odoo>
```

- [ ] **Paso 7: manifest `data`** (las vistas se suman en la tarea 5):

```python
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
    ],
```

- [ ] **Paso 8: descomentar** los tres modelos en `models/__init__.py`. Actualizar el módulo
(`-u`, sin tests): carga sin errores.

- [ ] **Paso 9: commit**

```bash
git add alpardata_supplier_pricelist_import
git commit -m "feat(supplier_pricelist_import): modelos de perfil, importación y líneas"
```

---

### Tarea 3: Vista previa

**Files:** Modify `models/supplier_pricelist_import.py`; Create `tests/common.py`,
`tests/test_preview.py`.

- [ ] **Paso 1: `tests/common.py`**

```python
from __future__ import annotations

import base64
import io

import openpyxl

from odoo.tests.common import TransactionCase


def xlsx_b64(rows):
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue())


class ImportCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({
            'name': 'Distribuidora Test',
            'purchase_discount_cascade': '10',
        })
        cls.categ = cls.env['product.category'].create({'name': 'Gaseosas Test'})
        cls.categ_child = cls.env['product.category'].create({
            'name': 'Colas Test', 'parent_id': cls.categ.id,
        })
        cls.other_categ = cls.env['product.category'].create({'name': 'Otros Test'})
        cls.p1 = cls._product('Cola 2L', cls.categ_child, barcode='7790001', default_code='COLA2')
        cls.p2 = cls._product('Lima 2L', cls.categ, barcode='7790002', default_code='LIMA2')
        cls.p3 = cls._product('Yerba 1kg', cls.other_categ, barcode='7790003', default_code='YER1')
        cls.s1 = cls._seller(cls.p1, 'A1', 100.0)
        cls.s2 = cls._seller(cls.p2, 'A2', 200.0)
        cls.s3 = cls._seller(cls.p3, 'A3', 300.0)
        cls.profile = cls.env['supplier.pricelist.import.profile'].create({
            'name': 'Excel Distribuidora',
            'partner_id': cls.partner.id,
            'col_code': 'Código',
            'col_price': 'Precio',
        })

    @classmethod
    def _product(cls, name, categ, **vals):
        return cls.env['product.product'].create({'name': name, 'categ_id': categ.id, **vals})

    @classmethod
    def _seller(cls, product, code, cost):
        return cls.env['product.supplierinfo'].create({
            'partner_id': cls.partner.id,
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_code': code,
            'price': cost,
            'reference_cost': cost,
        })

    def _file_import(self, rows, **vals):
        return self.env['supplier.pricelist.import'].create({
            'partner_id': self.partner.id,
            'mode': 'file',
            'profile_id': self.profile.id,
            'file': xlsx_b64(rows),
            'file_name': 'lista.xlsx',
            **vals,
        })

    def _line(self, imp, code):
        return imp.line_ids.filtered(lambda l: l.code == code)
```

- [ ] **Paso 2: test que falla** — `tests/test_preview.py`

```python
from __future__ import annotations

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ImportCommon


@tagged('post_install', '-at_install')
class TestPreview(ImportCommon):

    def test_statuses(self):
        imp = self._file_import([
            ['Código', 'Precio'],
            ['A1', 110],        # cambia
            ['A2', 200],        # sin cambio
            ['ZZ', 50],         # no encontrado
            ['A3', 'abc'],      # error
            ['A1', 120],        # duplicado
            [None, 999],        # sin código: se ignora
        ])
        imp.action_preview()
        self.assertEqual(imp.state, 'preview')
        self.assertEqual(self._line(imp, 'A1').mapped('status'), ['change', 'error'])
        self.assertEqual(self._line(imp, 'A2').status, 'unchanged')
        self.assertEqual(self._line(imp, 'ZZ').status, 'not_found')
        self.assertEqual(self._line(imp, 'A3').status, 'error')
        self.assertEqual(len(imp.line_ids), 5)

    def test_change_values(self):
        imp = self._file_import([['Código', 'Precio'], ['A1', 110]])
        imp.action_preview()
        line = self._line(imp, 'A1')
        self.assertEqual(line.supplierinfo_id, self.s1)
        self.assertEqual(line.old_list_price, 100.0)
        self.assertEqual(line.new_list_price, 110.0)
        self.assertAlmostEqual(line.variation_pct, 10.0)
        # bonificación del proveedor 10 %
        self.assertAlmostEqual(line.old_replacement_cost, 90.0)
        self.assertAlmostEqual(line.new_replacement_cost, 99.0)
        self.assertTrue(line.to_apply)

    def test_match_by_barcode_and_default_code(self):
        self.profile.match_by = 'barcode'
        imp = self._file_import([['Código', 'Precio'], ['7790001', 110]])
        imp.action_preview()
        self.assertEqual(self._line(imp, '7790001').supplierinfo_id, self.s1)
        self.profile.match_by = 'default_code'
        imp2 = self._file_import([['Código', 'Precio'], ['LIMA2', 210]])
        imp2.action_preview()
        self.assertEqual(self._line(imp2, 'LIMA2').supplierinfo_id, self.s2)

    def test_price_includes_vat(self):
        self.profile.price_includes_vat = True
        imp = self._file_import([['Código', 'Precio'], ['A1', 121]])
        imp.action_preview()
        self.assertAlmostEqual(self._line(imp, 'A1').new_list_price, 100.0)
        self.assertEqual(self._line(imp, 'A1').status, 'unchanged')

    def test_cascade_column(self):
        self.profile.col_cascade = 'Bonif'
        imp = self._file_import([['Código', 'Precio', 'Bonif'], ['A1', 100, '20']])
        imp.action_preview()
        line = self._line(imp, 'A1')
        self.assertEqual(line.status, 'change')
        self.assertEqual(line.old_cascade, '10')
        self.assertEqual(line.new_cascade, '20')
        self.assertAlmostEqual(line.new_replacement_cost, 80.0)

    def test_missing_column(self):
        imp = self._file_import([['Cod', 'Precio'], ['A1', 1]])
        with self.assertRaises(UserError):
            imp.action_preview()

    def test_percent_mode_with_filters(self):
        imp = self.env['supplier.pricelist.import'].create({
            'partner_id': self.partner.id,
            'mode': 'percent',
            'percent': 8.0,
            'filter_categ_ids': [(6, 0, self.categ.ids)],
        })
        imp.action_preview()
        self.assertEqual(
            imp.line_ids.mapped('supplierinfo_id'), self.s1 | self.s2,
            'Incluye la subcategoría y excluye otras categorías',
        )
        self.assertAlmostEqual(self._line(imp, 'A1').new_list_price, 108.0)

    def test_preview_regenerates(self):
        imp = self._file_import([['Código', 'Precio'], ['A1', 110]])
        imp.action_preview()
        imp.action_preview()
        self.assertEqual(len(imp.line_ids), 1)
```

- [ ] **Paso 3: correr** → falla (`action_preview` no existe). Descomentar `test_preview`.

- [ ] **Paso 4: agregar a `models/supplier_pricelist_import.py`** (imports arriba):

```python
from odoo.tools import float_compare

from odoo.addons.alpardata_purchase_replacement_cost.tools import (
    cascade_equivalent_pct,
    compute_replacement_cost,
    parse_discount_cascade,
)

from ..tools.readers import normalize_header, parse_number, read_csv, read_xlsx
```

y los métodos dentro de la clase:

```python
    # ── Vista previa ──────────────────────────────────────────────────────────
    def action_preview(self) -> None:
        self.ensure_one()
        if self.state not in ('draft', 'preview'):
            raise UserError(_('Sólo se puede generar la vista previa en borrador.'))
        self.line_ids.unlink()
        if self.mode == 'file':
            vals_list = self._preview_from_file()
        else:
            vals_list = self._preview_from_percent()
        self.env['supplier.pricelist.import.line'].create(vals_list)
        self.state = 'preview'

    def _seller_for(self, template):
        return template.with_company(self.company_id)._get_reference_cost_seller(
            partner=self.partner_id,
        )

    def _line_vals(self, seller, new_price, new_cascade=None, row_number=0, code=False) -> dict:
        """Valores de una línea con proveedor encontrado y precio válido."""
        old_price = seller.reference_cost
        old_cascade = seller.effective_discount_cascade or False
        cascade = old_cascade if new_cascade is None else (new_cascade or False)
        tmpl = seller.product_tmpl_id
        _net, new_replacement = compute_replacement_cost(
            new_price,
            cascade_equivalent_pct(parse_discount_cascade(cascade)),
            seller.effective_early_payment_pct,
            seller.effective_freight_pct,
            seller.effective_perception_pct,
            tmpl.internal_tax_pct,
        )
        changed = (
            float_compare(new_price, old_price, precision_digits=4) != 0
            or (cascade or False) != old_cascade
        )
        return {
            'import_id': self.id,
            'row_number': row_number,
            'code': code,
            'supplierinfo_id': seller.id,
            'product_tmpl_id': tmpl.id,
            'old_list_price': old_price,
            'new_list_price': new_price,
            'variation_pct': ((new_price / old_price) - 1) * 100 if old_price else 0.0,
            'old_cascade': old_cascade,
            'new_cascade': cascade,
            'old_replacement_cost': seller.replacement_cost,
            'new_replacement_cost': new_replacement,
            'status': 'change' if changed else 'unchanged',
            'to_apply': changed,
        }

    def _preview_from_percent(self) -> list[dict]:
        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('company_id', 'in', [self.company_id.id, False]),
        ]
        if self.filter_categ_ids:
            domain.append(('product_tmpl_id.categ_id', 'child_of', self.filter_categ_ids.ids))
        if self.filter_tag_ids:
            domain.append(('product_tmpl_id.product_tag_ids', 'in', self.filter_tag_ids.ids))
        templates = self.env['product.supplierinfo'].search(domain).product_tmpl_id
        vals_list = []
        for tmpl in templates:
            seller = self._seller_for(tmpl)
            if not seller:
                continue
            new_price = seller.reference_cost * (1 + self.percent / 100)
            vals_list.append(self._line_vals(seller, new_price, code=seller.product_code))
        return vals_list

    def _read_file_rows(self):
        profile = self.profile_id
        if not profile or not self.file:
            raise UserError(_('Elegí un perfil y cargá el archivo.'))
        content = base64.b64decode(self.file)
        try:
            if profile.file_type == 'xlsx':
                return read_xlsx(content, profile.sheet_name, profile.header_row)
            return read_csv(
                content, profile.csv_delimiter or ';', profile.csv_encoding or 'utf-8',
                profile.header_row,
            )
        except (ValueError, UnicodeDecodeError, KeyError, OSError) as err:
            raise UserError(_('No se pudo leer el archivo: %s', err)) from err
        except Exception as err:  # openpyxl levanta errores propios con archivos rotos
            raise UserError(_('No se pudo leer el archivo: %s', err)) from err

    def _find_template(self, code: str):
        match_by = self.profile_id.match_by
        if match_by == 'supplier_code':
            sellers = self.env['product.supplierinfo'].search([
                ('partner_id', '=', self.partner_id.id),
                ('product_code', '=', code),
                ('company_id', 'in', [self.company_id.id, False]),
            ])
            return sellers.product_tmpl_id[:1]
        field = 'barcode' if match_by == 'barcode' else 'default_code'
        return self.env['product.product'].search([(field, '=', code)], limit=1).product_tmpl_id

    def _preview_from_file(self) -> list[dict]:
        profile = self.profile_id
        rows = self._read_file_rows()
        col_code = normalize_header(profile.col_code)
        col_price = normalize_header(profile.col_price)
        col_cascade = normalize_header(profile.col_cascade) if profile.col_cascade else False
        headers = set(rows[0][1]) if rows else set()
        missing = [
            original for original, normalized in (
                (profile.col_code, col_code), (profile.col_price, col_price),
                (profile.col_cascade, col_cascade),
            ) if normalized and headers and normalized not in headers
        ]
        if missing:
            raise UserError(_(
                'Columnas no encontradas en el archivo: %s. Encabezados leídos: %s.',
                ', '.join(missing), ', '.join(sorted(headers)),
            ))
        decimal = profile.csv_decimal or ','
        seen: dict[str, int] = {}
        vals_list = []
        for row_number, data in rows:
            raw_code = data.get(col_code)
            if raw_code in (None, ''):
                continue
            code = str(raw_code).strip()
            if isinstance(raw_code, float) and raw_code.is_integer():
                code = str(int(raw_code))
            base = {'import_id': self.id, 'row_number': row_number, 'code': code}
            if code in seen:
                vals_list.append({**base, 'status': 'error',
                                  'message': _('Código duplicado en fila %s', seen[code])})
                continue
            seen[code] = row_number
            price = parse_number(data.get(col_price), decimal)
            if price is None or price <= 0:
                vals_list.append({**base, 'status': 'error',
                                  'message': _('Precio inválido: %s', data.get(col_price))})
                continue
            if profile.price_includes_vat:
                price = price / (1 + profile.vat_pct / 100)
            new_cascade = None
            if col_cascade:
                raw_cascade = data.get(col_cascade)
                new_cascade = str(raw_cascade).strip() if raw_cascade not in (None, '') else ''
                if isinstance(raw_cascade, float) and raw_cascade.is_integer():
                    new_cascade = str(int(raw_cascade))
                try:
                    parse_discount_cascade(new_cascade)
                except ValueError as err:
                    vals_list.append({**base, 'status': 'error', 'message': str(err)})
                    continue
            template = self._find_template(code)
            seller = self._seller_for(template) if template else False
            if not seller:
                vals_list.append({**base, 'status': 'not_found',
                                  'message': _('Producto o ficha del proveedor no encontrados')})
                continue
            vals_list.append(self._line_vals(seller, price, new_cascade, row_number, code))
        return vals_list
```

> El test `test_cascade_column` compara `new_cascade == '20'`: la cascada del archivo
> reemplaza a la vigente. Una celda vacía en esa columna significa "sin bonificación".

- [ ] **Paso 5: correr** → `TestPreview` pasa.

- [ ] **Paso 6: commit**

```bash
git add alpardata_supplier_pricelist_import
git commit -m "feat(supplier_pricelist_import): vista previa desde archivo y por porcentaje"
```

---

### Tarea 4: Aplicar y cancelar

**Files:** Modify `models/supplier_pricelist_import.py`; Create `tests/test_apply.py`.

- [ ] **Paso 1: test que falla** — `tests/test_apply.py`

```python
from __future__ import annotations

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import ImportCommon


@tagged('post_install', '-at_install')
class TestApply(ImportCommon):

    def test_apply_today(self):
        imp = self._file_import([['Código', 'Precio'], ['A1', 110], ['A2', 250]])
        imp.action_preview()
        self._line(imp, 'A2').to_apply = False
        imp.action_apply()
        self.assertEqual(imp.state, 'done')
        self.assertEqual(self.p1.product_tmpl_id.reference_cost, 110.0)
        self.assertEqual(self.p2.product_tmpl_id.reference_cost, 200.0)
        self.assertEqual(self.s1.date_end, fields.Date.today() - timedelta(days=1))
        history = self.env['product.supplierinfo.cost.history'].search([
            ('product_tmpl_id', '=', self.p1.product_tmpl_id.id),
        ], order='id desc', limit=1)
        self.assertIn(imp.name, history.change_reason)

    def test_apply_future_date(self):
        future = fields.Date.today() + timedelta(days=10)
        imp = self._file_import([['Código', 'Precio'], ['A1', 110]], effective_date=future)
        imp.action_preview()
        imp.action_apply()
        self.assertEqual(self.p1.product_tmpl_id.reference_cost, 100.0)
        new_seller = self.p1.product_tmpl_id.seller_ids.filtered(lambda s: s.date_start == future)
        self.assertEqual(new_seller.reference_cost, 110.0)

    def test_apply_cascade_from_file(self):
        self.profile.col_cascade = 'Bonif'
        imp = self._file_import([['Código', 'Precio', 'Bonif'], ['A1', 100, '20']])
        imp.action_preview()
        imp.action_apply()
        tmpl = self.p1.product_tmpl_id
        seller = tmpl._get_reference_cost_seller()
        self.assertTrue(seller.use_own_conditions)
        self.assertEqual(seller.own_discount_cascade, '20')
        self.assertAlmostEqual(tmpl.replacement_cost, 80.0)

    def test_new_seller_keeps_code(self):
        imp = self._file_import([['Código', 'Precio'], ['A1', 110]])
        imp.action_preview()
        imp.action_apply()
        seller = self.p1.product_tmpl_id._get_reference_cost_seller()
        self.assertEqual(seller.product_code, 'A1')

    def test_buyer_cannot_apply(self):
        buyer = new_test_user(self.env, login='buyer_spl', groups='purchase.group_purchase_user')
        imp = self._file_import([['Código', 'Precio'], ['A1', 110]])
        imp.action_preview()
        with self.assertRaises(AccessError):
            imp.with_user(buyer).action_apply()

    def test_apply_requires_preview(self):
        imp = self._file_import([['Código', 'Precio'], ['A1', 110]])
        with self.assertRaises(UserError):
            imp.action_apply()

    def test_cancel(self):
        imp = self._file_import([['Código', 'Precio'], ['A1', 110]])
        imp.action_cancel()
        self.assertEqual(imp.state, 'cancelled')
```

- [ ] **Paso 2: correr** → falla. Descomentar `test_apply`.

- [ ] **Paso 3: agregar a `models/supplier_pricelist_import.py`**

```python
    # ── Aplicar ───────────────────────────────────────────────────────────────
    _COPIED_SELLER_FIELDS = (
        'partner_id', 'product_tmpl_id', 'product_id', 'company_id', 'product_code',
        'product_name', 'product_uom_id', 'currency_id', 'min_qty', 'sequence', 'delay',
        'price', 'discount', 'use_own_conditions', 'own_discount_cascade',
        'own_early_payment_pct', 'own_freight_pct', 'own_perception_pct',
    )

    def _new_seller_vals(self, line) -> dict:
        seller = line.supplierinfo_id
        vals = {}
        for name in self._COPIED_SELLER_FIELDS:
            value = seller[name]
            vals[name] = value.id if isinstance(value, models.BaseModel) else value
        vals.update({
            'reference_cost': line.new_list_price,
            'date_start': self.effective_date,
            'date_end': False,
        })
        if line.new_cascade != line.old_cascade:
            vals.update({
                'use_own_conditions': True,
                'own_discount_cascade': line.new_cascade or False,
            })
            if not seller.use_own_conditions:
                # Al pasar a condiciones propias se conservan las del proveedor
                vals.update({
                    'own_early_payment_pct': seller.effective_early_payment_pct,
                    'own_freight_pct': seller.effective_freight_pct,
                    'own_perception_pct': seller.effective_perception_pct,
                })
        return vals

    def action_apply(self) -> None:
        self.ensure_one()
        if not self.env.user.has_group('purchase.group_purchase_manager'):
            raise AccessError(_('Sólo los gerentes de compras pueden aplicar listas de proveedores.'))
        if self.state != 'preview':
            raise UserError(_('Generá la vista previa antes de aplicar.'))
        lines = self.line_ids.filtered(lambda l: l.status == 'change' and l.to_apply)
        vals_list = [self._new_seller_vals(line) for line in lines]
        self.env['product.supplierinfo'].with_context(
            _change_reason=_('Importación %s', self.name),
        ).create(vals_list)
        self.write({
            'state': 'done',
            'applied_date': fields.Datetime.now(),
            'applied_by': self.env.uid,
        })
        self.message_post(body=_(
            'Lista aplicada: %(applied)s fichas actualizadas desde %(date)s '
            '(%(skipped)s cambios no aplicados, %(nf)s no encontrados, %(err)s errores).',
            applied=len(lines), date=self.effective_date,
            skipped=self.count_change - len(lines),
            nf=self.count_not_found, err=self.count_error,
        ))

    def action_cancel(self) -> None:
        for rec in self:
            if rec.state == 'done':
                raise UserError(_('No se puede cancelar una importación aplicada.'))
        self.write({'state': 'cancelled'})

    def action_reset_draft(self) -> None:
        self.filtered(lambda r: r.state == 'cancelled').write({'state': 'draft'})
```

> `create` en lote dispara el `create` del módulo base, que por cada registro registra el
> historial y cierra la vigencia anterior (`_close_previous_records`). No reimplementarlo.
> El supplierinfo se crea sin `sudo`: el manager tiene permisos; así las reglas de acceso
> se respetan.

- [ ] **Paso 4: correr** → `TestApply` pasa. Si `test_apply_today` falla porque el nuevo
supplierinfo no gana en el resolver (misma `sequence`, mismo día), revisar que el anterior
quedó con `date_end = ayer` (lo hace el base); no cambiar la `sequence`.

- [ ] **Paso 5: commit**

```bash
git add alpardata_supplier_pricelist_import
git commit -m "feat(supplier_pricelist_import): aplicar y cancelar importaciones"
```

---

### Tarea 5: Vistas, menús y smart button del proveedor

**Files:** Create `models/res_partner.py`, las 4 vistas; Modify manifest.

- [ ] **Paso 1: `models/res_partner.py`**

```python
from __future__ import annotations

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    supplier_pricelist_import_count = fields.Integer(
        compute='_compute_supplier_pricelist_import_count',
    )

    def _compute_supplier_pricelist_import_count(self) -> None:
        data = self.env['supplier.pricelist.import']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'],
        )
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.supplier_pricelist_import_count = counts.get(partner.id, 0)

    def action_view_supplier_pricelist_imports(self) -> dict:
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Listas importadas',
            'res_model': 'supplier.pricelist.import',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
```

Descomentar `res_partner` en `models/__init__.py`.

- [ ] **Paso 2: `views/supplier_pricelist_import_profile_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="spl_profile_view_list" model="ir.ui.view">
        <field name="name">supplier.pricelist.import.profile.list</field>
        <field name="model">supplier.pricelist.import.profile</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="partner_id"/>
                <field name="file_type"/>
                <field name="match_by"/>
                <field name="company_id" groups="base.group_multi_company"/>
            </list>
        </field>
    </record>

    <record id="spl_profile_view_form" model="ir.ui.view">
        <field name="name">supplier.pricelist.import.profile.form</field>
        <field name="model">supplier.pricelist.import.profile</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <group>
                        <group string="Proveedor">
                            <field name="name"/>
                            <field name="partner_id"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                            <field name="active" invisible="1"/>
                        </group>
                        <group string="Archivo">
                            <field name="file_type"/>
                            <field name="sheet_name" invisible="file_type != 'xlsx'"/>
                            <field name="header_row"/>
                            <field name="csv_delimiter" invisible="file_type != 'csv'"/>
                            <field name="csv_encoding" invisible="file_type != 'csv'"/>
                            <field name="csv_decimal"/>
                        </group>
                        <group string="Columnas">
                            <field name="match_by"/>
                            <field name="col_code" placeholder="Código"/>
                            <field name="col_price" placeholder="Precio"/>
                            <field name="col_cascade" placeholder="Bonificación"/>
                        </group>
                        <group string="Precio">
                            <field name="price_includes_vat"/>
                            <field name="vat_pct" invisible="not price_includes_vat"/>
                        </group>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_spl_profile" model="ir.actions.act_window">
        <field name="name">Perfiles de listas de proveedores</field>
        <field name="res_model">supplier.pricelist.import.profile</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Paso 3: `views/supplier_pricelist_import_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="spl_import_view_list" model="ir.ui.view">
        <field name="name">supplier.pricelist.import.list</field>
        <field name="model">supplier.pricelist.import</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="partner_id"/>
                <field name="mode"/>
                <field name="effective_date"/>
                <field name="count_change"/>
                <field name="applied_by" optional="show"/>
                <field name="state" widget="badge"
                       decoration-info="state == 'preview'"
                       decoration-success="state == 'done'"
                       decoration-muted="state == 'cancelled'"/>
            </list>
        </field>
    </record>

    <record id="spl_import_view_form" model="ir.ui.view">
        <field name="name">supplier.pricelist.import.form</field>
        <field name="model">supplier.pricelist.import</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_preview" type="object" string="Generar vista previa"
                            class="btn-primary" invisible="state != 'draft'"/>
                    <button name="action_preview" type="object" string="Regenerar vista previa"
                            invisible="state != 'preview'"/>
                    <button name="action_apply" type="object" string="Aplicar"
                            class="btn-primary" invisible="state != 'preview'"
                            groups="purchase.group_purchase_manager"
                            confirm="Se crearán nuevas fichas de proveedor con vigencia desde la fecha indicada. ¿Continuar?"/>
                    <button name="action_cancel" type="object" string="Cancelar"
                            invisible="state not in ('draft', 'preview')"/>
                    <button name="action_reset_draft" type="object" string="Volver a borrador"
                            invisible="state != 'cancelled'"/>
                    <field name="state" widget="statusbar" statusbar_visible="draft,preview,done"/>
                </header>
                <sheet>
                    <div class="oe_title">
                        <h1><field name="name"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="partner_id" readonly="state != 'draft'"/>
                            <field name="company_id" groups="base.group_multi_company"
                                   readonly="state != 'draft'"/>
                            <field name="mode" widget="radio" readonly="state != 'draft'"/>
                            <field name="effective_date" readonly="state == 'done'"/>
                        </group>
                        <group invisible="mode != 'file'">
                            <field name="profile_id" required="mode == 'file'"
                                   readonly="state != 'draft'"/>
                            <field name="file" filename="file_name" required="mode == 'file'"
                                   readonly="state != 'draft'"/>
                            <field name="file_name" invisible="1"/>
                        </group>
                        <group invisible="mode != 'percent'">
                            <field name="percent" readonly="state != 'draft'"/>
                            <field name="filter_categ_ids" widget="many2many_tags"
                                   readonly="state != 'draft'"/>
                            <field name="filter_tag_ids" widget="many2many_tags"
                                   readonly="state != 'draft'"/>
                        </group>
                    </group>
                    <group invisible="state == 'draft'">
                        <field name="count_change"/>
                        <field name="count_unchanged"/>
                        <field name="count_not_found"/>
                        <field name="count_error"/>
                    </group>
                    <notebook invisible="state == 'draft'">
                        <page string="Líneas" name="lines">
                            <field name="line_ids" readonly="state != 'preview'">
                                <list editable="bottom" create="0" delete="0"
                                      decoration-muted="status == 'unchanged'"
                                      decoration-danger="status == 'error'"
                                      decoration-warning="status == 'not_found'">
                                    <field name="to_apply" readonly="status != 'change'"/>
                                    <field name="row_number" optional="show" readonly="1"/>
                                    <field name="code" readonly="1"/>
                                    <field name="product_tmpl_id" readonly="1"/>
                                    <field name="old_list_price" readonly="1"/>
                                    <field name="new_list_price" readonly="1"/>
                                    <field name="variation_pct" readonly="1"
                                           decoration-danger="variation_pct &gt; 0"
                                           decoration-success="variation_pct &lt; 0"/>
                                    <field name="old_cascade" optional="hide" readonly="1"/>
                                    <field name="new_cascade" optional="hide" readonly="1"/>
                                    <field name="old_replacement_cost" optional="show" readonly="1"/>
                                    <field name="new_replacement_cost" optional="show" readonly="1"/>
                                    <field name="status" readonly="1"/>
                                    <field name="message" optional="show" readonly="1"/>
                                </list>
                            </field>
                        </page>
                    </notebook>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="spl_import_view_search" model="ir.ui.view">
        <field name="name">supplier.pricelist.import.search</field>
        <field name="model">supplier.pricelist.import</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="partner_id"/>
                <filter name="filter_preview" string="En vista previa" domain="[('state', '=', 'preview')]"/>
                <filter name="filter_done" string="Aplicadas" domain="[('state', '=', 'done')]"/>
                <group>
                    <filter name="group_partner" string="Proveedor" context="{'group_by': 'partner_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_spl_import" model="ir.actions.act_window">
        <field name="name">Importar listas de proveedores</field>
        <field name="res_model">supplier.pricelist.import</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Paso 4: `views/res_partner_views.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_partner_form_spl_button" model="ir.ui.view">
        <field name="name">res.partner.form.spl.button</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <xpath expr="//div[@name='button_box']" position="inside">
                <button name="action_view_supplier_pricelist_imports" type="object"
                        class="oe_stat_button" icon="fa-upload"
                        groups="purchase.group_purchase_user"
                        invisible="supplier_pricelist_import_count == 0">
                    <field name="supplier_pricelist_import_count" widget="statinfo"
                           string="Listas importadas"/>
                </button>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Paso 5: `views/menus.xml`**

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_spl_import"
              name="Importar listas de proveedores"
              parent="purchase.menu_purchase_products"
              action="action_spl_import"
              sequence="30"/>
    <menuitem id="menu_spl_profile"
              name="Perfiles de listas de proveedores"
              parent="purchase.menu_purchase_config"
              action="action_spl_profile"
              groups="purchase.group_purchase_manager"
              sequence="40"/>
</odoo>
```

> Verificar en `odoo-19.0/addons/purchase/views/purchase_views.xml` que existan
> `purchase.menu_purchase_products` y `purchase.menu_purchase_config`; si cambiaron de id,
> usar los reales.

- [ ] **Paso 6: manifest `data`** completo:

```python
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/supplier_pricelist_import_profile_views.xml',
        'views/supplier_pricelist_import_views.xml',
        'views/res_partner_views.xml',
        'views/menus.xml',
    ],
```

- [ ] **Paso 7: actualizar módulo y correr todos los tests** → 0 fallas.

- [ ] **Paso 8: prueba manual** (anotar en el PR): crear perfil, subir un xlsx con 3
productos (uno inexistente), generar vista previa, destildar uno, aplicar; verificar la
ficha del producto y el historial.

- [ ] **Paso 9: commit**

```bash
git add alpardata_supplier_pricelist_import
git commit -m "feat(supplier_pricelist_import): vistas, menús y botón en el proveedor"
```

---

### Tarea 6: README y PR

- [ ] **Paso 1: `README.md`**: para qué sirve, cómo armar un perfil (fila de encabezados,
nombres de columna, IVA incluido), modo porcentaje, qué hace "Aplicar" (nueva ficha con
vigencia; la anterior se cierra; historial con el número de importación), permisos,
limitaciones (no crea productos; columnas por nombre de encabezado).
- [ ] **Paso 2: commit, push y PR contra `19.0`.**

```bash
git add alpardata_supplier_pricelist_import/README.md
git commit -m "docs(supplier_pricelist_import): README"
git push -u origin feat/supplier-pricelist-import
```
