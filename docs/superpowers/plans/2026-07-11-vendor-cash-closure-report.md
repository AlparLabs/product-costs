# Vendor Cash Closure Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `sale_vendor_cash_closure` Odoo 19 module: a date wizard that generates a "Cierre de Caja" PDF + XLSX, listing every posted customer invoice/credit note and customer payment for a day, grouped by salesperson, split into Contado / Cuenta Corriente / NC / MiPyme (FCE) columns with per-vendor and grand-total subtotals.

**Architecture:** All business logic (classification, discount math, vendor/pricelist resolution, aggregation) lives in one `AbstractModel` (`report.sale_vendor_cash_closure.cash_closure_vendor`) exposing a single `_compute_data(date, company)` entry point. Both the QWeb PDF template and the XLSX exporter on the wizard consume that same data structure — zero duplicated business rules. The wizard is a thin `TransientModel` with two buttons.

**Tech Stack:** Odoo 19 (Python 3, QWeb, `xlsxwriter`), `account`, `sale`, `point_of_sale`, `l10n_latam_invoice_document`.

**Known verification risk:** a few native Odoo field names/values are assumed from prior knowledge and MUST be confirmed against the target Odoo 19 instance the first time their task's test runs:
- `res.partner.use_partner_credit_limit` (Task 2) — the credit-limit checkbox field.
- AFIP FCE document codes `201/206/211/202/207/212` (facturas/ND) and `203/208/213` (NC) on `l10n_latam.document.type.code` (Task 2).
- The exact required field set on `l10n_latam.document.type` used only to build test fixtures in Task 2 (`name`, `code`, `country_id`, `doc_code_prefix`) — if creation fails with a validation error, check Accounting → Configuration → Document Types for the real required fields and adjust the test fixture only (this model isn't touched by production code, just by test setup).

If a test fails with an `AttributeError` or unknown-field/validation error on these, open the target Odoo instance (Settings → Technical → Database Structure → Models) to find the real field name/codes and adjust the constant/field reference — the rest of the plan is unaffected.

---

### Task 1: Module skeleton

**Files:**
- Create: `sale_vendor_cash_closure/__init__.py`
- Create: `sale_vendor_cash_closure/__manifest__.py`
- Create: `sale_vendor_cash_closure/security/ir.model.access.csv`
- Create: `sale_vendor_cash_closure/report/__init__.py`
- Create: `sale_vendor_cash_closure/wizard/__init__.py`
- Create: `sale_vendor_cash_closure/tests/__init__.py`

- [ ] **Step 1: Create the root `__init__.py`**

```python
# sale_vendor_cash_closure/__init__.py
from . import report
from . import wizard
```

- [ ] **Step 2: Create the manifest**

```python
# sale_vendor_cash_closure/__manifest__.py
{
    'name': 'Vendor Cash Closure Report',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Daily sales/invoices closure report grouped by salesperson, for retail cash control',
    'description': """
        Replicates a legacy "Cierre de Caja" report: for a given date, lists
        every posted customer invoice/credit note and customer payment,
        grouped by salesperson, split into Contado / Cuenta Corriente / NC /
        MiPyme (FCE) columns, with per-vendor and grand-total subtotals.
        Downloadable as PDF (landscape) and XLSX from a date wizard.
    """,
    'author': 'AlparData',
    'website': 'https://www.alpardata.com.ar',
    'license': 'LGPL-3',
    'depends': ['account', 'sale', 'point_of_sale', 'l10n_latam_invoice_document'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
```

- [ ] **Step 3: Create the security access file**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_cash_closure_report_wizard_user,cash.closure.report.wizard user,model_cash_closure_report_wizard,account.group_account_invoice,1,1,1,1
access_cash_closure_report_wizard_manager,cash.closure.report.wizard manager,model_cash_closure_report_wizard,account.group_account_manager,1,1,1,1
```

- [ ] **Step 4: Create empty package `__init__.py` files**

```python
# sale_vendor_cash_closure/report/__init__.py
```

```python
# sale_vendor_cash_closure/wizard/__init__.py
```

```python
# sale_vendor_cash_closure/tests/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/__init__.py sale_vendor_cash_closure/__manifest__.py sale_vendor_cash_closure/security/ir.model.access.csv sale_vendor_cash_closure/report/__init__.py sale_vendor_cash_closure/wizard/__init__.py sale_vendor_cash_closure/tests/__init__.py
git commit -m "feat(sale_vendor_cash_closure): module skeleton"
```

The module is installable at this point (only the security CSV is declared in `data`). Tasks 8 and 9 will each append one new XML file to the manifest's `data` list as they create it.

---

### Task 2: Move classification (Contado / Cta.Cte / NC / MiPyme)

**Files:**
- Create: `sale_vendor_cash_closure/report/report_cash_closure_vendor.py`
- Create: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

```python
# sale_vendor_cash_closure/tests/test_cash_closure_report.py
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo import fields


@tagged('post_install', '-at_install')
class TestCashClosureReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report_model = cls.env['report.sale_vendor_cash_closure.cash_closure_vendor']
        cls.today = fields.Date.today()

        cls.product = cls.env['product.product'].create({
            'name': 'Producto Test',
            'type': 'service',
            'lst_price': 100.0,
        })

        cls.partner_contado = cls.env['res.partner'].create({
            'name': 'Cliente Contado',
            'use_partner_credit_limit': False,
        })
        cls.partner_ctacte = cls.env['res.partner'].create({
            'name': 'Cliente Cuenta Corriente',
            'use_partner_credit_limit': True,
        })

        # Generic LATAM document types (from l10n_latam_invoice_document),
        # not tied to a specific AFIP posting flow — enough to exercise
        # the classification logic without needing full AR CAE setup.
        country_ar = cls.env.ref('base.ar')
        cls.doc_type_normal = cls.env['l10n_latam.document.type'].create({
            'name': 'Factura Test',
            'code': '999',
            'country_id': country_ar.id,
            'doc_code_prefix': 'FA-',
        })
        cls.doc_type_fce_invoice = cls.env['l10n_latam.document.type'].create({
            'name': 'FCE Factura MiPyme A Test',
            'code': '201',
            'country_id': country_ar.id,
            'doc_code_prefix': 'FCE-',
        })
        cls.doc_type_fce_credit = cls.env['l10n_latam.document.type'].create({
            'name': 'FCE Nota de Crédito MiPyme A Test',
            'code': '203',
            'country_id': country_ar.id,
            'doc_code_prefix': 'NCF-',
        })

    def _create_move(self, partner, move_type='out_invoice', doc_type=None, price_unit=100.0, discount=0.0):
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': self.today,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': price_unit,
                'discount': discount,
            })],
        })
        if doc_type:
            move.l10n_latam_document_type_id = doc_type.id
        return move

    def test_classify_contado_invoice(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal)
        self.assertEqual(self.report_model._classify_move(move), 'contado')

    def test_classify_ctacte_invoice(self):
        move = self._create_move(self.partner_ctacte, doc_type=self.doc_type_normal)
        self.assertEqual(self.report_model._classify_move(move), 'cta_cte_nd')

    def test_classify_contado_refund(self):
        move = self._create_move(self.partner_contado, move_type='out_refund', doc_type=self.doc_type_normal)
        self.assertEqual(self.report_model._classify_move(move), 'nc_contado')

    def test_classify_ctacte_refund(self):
        move = self._create_move(self.partner_ctacte, move_type='out_refund', doc_type=self.doc_type_normal)
        self.assertEqual(self.report_model._classify_move(move), 'nc_dev_ctacte_dia')

    def test_classify_fce_invoice_overrides_partner(self):
        # Partner is CtaCte, but the FCE document type takes priority.
        move = self._create_move(self.partner_ctacte, doc_type=self.doc_type_fce_invoice)
        self.assertEqual(self.report_model._classify_move(move), 'fact_mipyme')

    def test_classify_fce_credit_note(self):
        move = self._create_move(self.partner_contado, move_type='out_refund', doc_type=self.doc_type_fce_credit)
        self.assertEqual(self.report_model._classify_move(move), 'nc_mipyme')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -i sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test` (reemplazar `odoo19_dev` por tu base de datos de desarrollo)
Expected: FAIL — `report.sale_vendor_cash_closure.cash_closure_vendor` model does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Update `report/__init__.py` so the new model file is actually imported and registered by Odoo:

```python
# sale_vendor_cash_closure/report/__init__.py
from . import report_cash_closure_vendor
```

```python
# sale_vendor_cash_closure/report/report_cash_closure_vendor.py
from odoo import models


FCE_DEBIT_CODES = {'201', '206', '211', '202', '207', '212'}
FCE_CREDIT_CODES = {'203', '208', '213'}

AMOUNT_COLUMNS = [
    'contado', 'cta_cte_nd', 'nc_contado', 'dev_ctacte_dia_ant',
    'nc_dev_ctacte_dia', 'fact_mipyme', 'nc_mipyme',
]
SUBTOTAL_KEYS = AMOUNT_COLUMNS + ['desct', 'cantidad_cc']

COLUMN_SPECS = [
    ('number', 'Comprobante'),
    ('partner_name', 'Cliente'),
    ('contado', 'Contado'),
    ('cta_cte_nd', 'Cta.Cte/ND'),
    ('nc_contado', 'N/C Cont.'),
    ('dev_ctacte_dia_ant', 'Dev.CtaCte D/Ant'),
    ('nc_dev_ctacte_dia', 'N/C Dev.CtaCte del Día'),
    ('fact_mipyme', 'Fact. MiPyme'),
    ('nc_mipyme', 'N/C MiPyme'),
    ('pct_desc', '% Desc'),
    ('desct', 'Desct.'),
    ('cantidad_cc', 'Cantid. CC'),
    ('lista', 'Lista'),
]


class ReportCashClosureVendor(models.AbstractModel):
    _name = 'report.sale_vendor_cash_closure.cash_closure_vendor'
    _description = 'Vendor Cash Closure Report'

    def _classify_move(self, move):
        """Return the column key where this move's amount_total belongs."""
        doc_code = move.l10n_latam_document_type_id.code or ''
        if doc_code in FCE_CREDIT_CODES:
            return 'nc_mipyme'
        if doc_code in FCE_DEBIT_CODES:
            return 'fact_mipyme'

        is_ctacte = move.commercial_partner_id.use_partner_credit_limit
        is_refund = move.move_type == 'out_refund'
        if is_refund:
            return 'nc_dev_ctacte_dia' if is_ctacte else 'nc_contado'
        return 'cta_cte_nd' if is_ctacte else 'contado'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 6 tests green. If `use_partner_credit_limit` or the `l10n_latam.document.type` fields error out, check the real field/model names on the target instance and adjust.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/report/__init__.py sale_vendor_cash_closure/report/report_cash_closure_vendor.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): classify moves into Contado/CtaCte/NC/MiPyme columns"
```

---

### Task 3: Discount computation

**Files:**
- Modify: `sale_vendor_cash_closure/report/report_cash_closure_vendor.py`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_compute_discount_no_discount(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0, discount=0.0)
        pct, amount = self.report_model._compute_discount(move)
        self.assertEqual(pct, 0.0)
        self.assertEqual(amount, 0.0)

    def test_compute_discount_with_discount(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0, discount=10.0)
        pct, amount = self.report_model._compute_discount(move)
        self.assertAlmostEqual(pct, 10.0, places=2)
        # 10% of 100 pre-tax = 10.0 discount, scaled by move's tax factor
        expected_amount = 10.0 * (move.amount_total / move.amount_untaxed)
        self.assertAlmostEqual(amount, expected_amount, places=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `_compute_discount` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `ReportCashClosureVendor` in `report_cash_closure_vendor.py`:

```python
    def _compute_discount(self, move):
        """Return (weighted % discount, tax-inclusive discount amount)."""
        lines = move.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note') and l.product_id
        )
        gross_untaxed = sum(line.price_unit * line.quantity for line in lines)
        net_untaxed = sum(line.price_subtotal for line in lines)
        discount_untaxed = gross_untaxed - net_untaxed

        tax_factor = (move.amount_total / move.amount_untaxed) if move.amount_untaxed else 1.0
        discount_amount = discount_untaxed * tax_factor
        pct_desc = (discount_untaxed / gross_untaxed * 100) if gross_untaxed else 0.0
        return pct_desc, discount_amount
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 8 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/report/report_cash_closure_vendor.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): compute weighted discount % and amount"
```

---

### Task 4: Vendor resolution (move + payment)

**Files:**
- Modify: `sale_vendor_cash_closure/report/report_cash_closure_vendor.py`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_resolve_move_vendor_falls_back_to_invoice_user(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal)
        move.invoice_user_id = self.env.user
        pos_order = self.env['pos.order']  # empty recordset: no linked POS order
        vendor_key, vendor_name = self.report_model._resolve_move_vendor(move, pos_order)
        self.assertEqual(vendor_key, ('res.users', self.env.user.id))
        self.assertEqual(vendor_name, self.env.user.name)

    def test_resolve_move_vendor_unassigned(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal)
        move.invoice_user_id = False
        pos_order = self.env['pos.order']
        vendor_key, vendor_name = self.report_model._resolve_move_vendor(move, pos_order)
        self.assertEqual(vendor_key, (False, False))
        self.assertEqual(vendor_name, 'Sin vendedor')

    def test_resolve_payment_vendor_from_partner_salesperson(self):
        self.partner_contado.user_id = self.env.user
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_contado.id,
            'amount': 500.0,
            'date': self.today,
        })
        vendor_key, vendor_name = self.report_model._resolve_payment_vendor(payment)
        self.assertEqual(vendor_key, ('res.users', self.env.user.id))
        self.assertEqual(vendor_name, self.env.user.name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `_resolve_move_vendor` / `_resolve_payment_vendor` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `ReportCashClosureVendor`:

```python
    def _resolve_move_vendor(self, move, pos_order):
        """Return ((model, id) key, display name) for the move's salesperson.

        `counter_salesperson_id` comes from the pos_centralized_payment
        module (separate repo) and may not be installed — the field
        presence check keeps this working either way.
        """
        if pos_order and 'counter_salesperson_id' in pos_order._fields and pos_order.counter_salesperson_id:
            employee = pos_order.counter_salesperson_id
            return ('hr.employee', employee.id), employee.name
        if move.invoice_user_id:
            return ('res.users', move.invoice_user_id.id), move.invoice_user_id.name
        return (False, False), 'Sin vendedor'

    def _resolve_payment_vendor(self, payment):
        salesperson = payment.partner_id.user_id
        if salesperson:
            return ('res.users', salesperson.id), salesperson.name
        return (False, False), 'Sin vendedor'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 11 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/report/report_cash_closure_vendor.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): resolve salesperson for moves and payments"
```

---

### Task 5: Pricelist resolution

**Files:**
- Modify: `sale_vendor_cash_closure/report/report_cash_closure_vendor.py`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_resolve_pricelist_from_sale_order(self):
        pricelist = self.env['product.pricelist'].create({'name': 'Lista Test'})
        sale_order = self.env['sale.order'].create({
            'partner_id': self.partner_contado.id,
            'pricelist_id': pricelist.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': 100.0,
            })],
        })
        sale_order.action_confirm()
        invoice_id = sale_order._create_invoices()
        pos_order = self.env['pos.order']
        result = self.report_model._resolve_pricelist(invoice_id, pos_order)
        self.assertEqual(result, 'Lista Test')

    def test_resolve_pricelist_empty_when_no_origin(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal)
        pos_order = self.env['pos.order']
        result = self.report_model._resolve_pricelist(move, pos_order)
        self.assertEqual(result, '')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `_resolve_pricelist` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `ReportCashClosureVendor`:

```python
    def _resolve_pricelist(self, move, pos_order):
        if pos_order and pos_order.pricelist_id:
            return pos_order.pricelist_id.name
        sale_orders = move.invoice_line_ids.sale_line_ids.mapped('order_id')
        if sale_orders and sale_orders[0].pricelist_id:
            return sale_orders[0].pricelist_id.name
        return ''
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 13 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/report/report_cash_closure_vendor.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): resolve price list from sale/POS origin"
```

---

### Task 6: Row builders

**Files:**
- Modify: `sale_vendor_cash_closure/report/report_cash_closure_vendor.py`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_build_move_row_contado(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0)
        vendor_key, vendor_name, row = self.report_model._build_move_row(move)
        self.assertEqual(vendor_key, (False, False))
        self.assertEqual(vendor_name, 'Sin vendedor')
        self.assertEqual(row['number'], move.name)
        self.assertEqual(row['partner_name'], self.partner_contado.name)
        self.assertEqual(row['contado'], move.amount_total)
        self.assertEqual(row['cta_cte_nd'], 0.0)
        self.assertEqual(row['cantidad_cc'], 0.0)

    def test_build_move_row_ctacte_sets_cantidad_cc(self):
        move = self._create_move(self.partner_ctacte, doc_type=self.doc_type_normal, price_unit=100.0)
        _key, _name, row = self.report_model._build_move_row(move)
        self.assertEqual(row['cta_cte_nd'], move.amount_total)
        self.assertEqual(row['cantidad_cc'], 1.0)

    def test_build_move_row_same_currency_amount_unchanged(self):
        # The common case (invoice currency == company currency): no FX
        # conversion should be applied, amount passes through as-is.
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0)
        self.assertEqual(move.currency_id, move.company_currency_id)
        _key, _name, row = self.report_model._build_move_row(move)
        self.assertEqual(row['contado'], move.amount_total)

    def test_build_payment_row(self):
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_ctacte.id,
            'amount': 750.0,
            'date': self.today,
        })
        vendor_key, vendor_name, row = self.report_model._build_payment_row(payment)
        self.assertEqual(vendor_key, (False, False))
        self.assertEqual(vendor_name, 'Sin vendedor')
        self.assertEqual(row['dev_ctacte_dia_ant'], 750.0)
        self.assertEqual(row['contado'], 0.0)
        self.assertEqual(row['lista'], '')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `_build_move_row` / `_build_payment_row` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `ReportCashClosureVendor`:

```python
    def _move_amount_company_currency(self, move):
        """Convert amount_total to the company currency using the move's
        exchange rate. Same formula already used in this repo's
        account_invoice_line_export (invoice_currency_rate is the
        company->invoice-currency ratio, so we divide to go the other way).
        """
        if move.currency_id == move.company_currency_id or not move.invoice_currency_rate:
            return move.amount_total
        return move.amount_total / move.invoice_currency_rate

    def _build_move_row(self, move):
        pos_order = self.env['pos.order'].search([('account_move', '=', move.id)], limit=1)
        column = self._classify_move(move)
        vendor_key, vendor_name = self._resolve_move_vendor(move, pos_order)
        pct_desc, discount_amount = self._compute_discount(move)

        row = {key: 0.0 for key in AMOUNT_COLUMNS}
        row[column] = self._move_amount_company_currency(move)
        row.update({
            'number': move.name or '',
            'partner_name': move.commercial_partner_id.name or '',
            'pct_desc': pct_desc,
            'desct': discount_amount,
            'cantidad_cc': 1.0 if column == 'cta_cte_nd' else 0.0,
            'lista': self._resolve_pricelist(move, pos_order),
        })
        return vendor_key, vendor_name, row

    def _build_payment_row(self, payment):
        vendor_key, vendor_name = self._resolve_payment_vendor(payment)

        row = {key: 0.0 for key in AMOUNT_COLUMNS}
        row['dev_ctacte_dia_ant'] = payment.amount
        row.update({
            'number': payment.name or payment.memo or '',
            'partner_name': payment.partner_id.name or '',
            'pct_desc': 0.0,
            'desct': 0.0,
            'cantidad_cc': 0.0,
            'lista': '',
        })
        return vendor_key, vendor_name, row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 17 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/report/report_cash_closure_vendor.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): build per-move and per-payment report rows"
```

---

### Task 7: Aggregation (`_compute_data`)

**Files:**
- Modify: `sale_vendor_cash_closure/report/report_cash_closure_vendor.py`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_compute_data_groups_and_totals(self):
        self.env.user.name = 'Vendedor Uno'
        move1 = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0)
        move1.invoice_user_id = self.env.user
        move1.action_post()

        move2 = self._create_move(self.partner_ctacte, doc_type=self.doc_type_normal, price_unit=200.0)
        move2.invoice_user_id = False  # falls into "Sin vendedor"
        move2.action_post()

        self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_ctacte.id,
            'amount': 50.0,
            'date': self.today,
        }).action_post()

        data = self.report_model._compute_data(self.today, self.env.company)

        self.assertEqual(data['date'], self.today)
        group_names = [g['salesperson_name'] for g in data['groups']]
        self.assertIn('Vendedor Uno', group_names)
        self.assertIn('Sin vendedor', group_names)
        # "Sin vendedor" must be sorted last
        self.assertEqual(group_names[-1], 'Sin vendedor')

        vendor_group = next(g for g in data['groups'] if g['salesperson_name'] == 'Vendedor Uno')
        self.assertEqual(vendor_group['subtotal']['contado'], move1.amount_total)

        unassigned_group = next(g for g in data['groups'] if g['salesperson_name'] == 'Sin vendedor')
        self.assertEqual(unassigned_group['subtotal']['cta_cte_nd'], move2.amount_total)
        self.assertEqual(unassigned_group['subtotal']['dev_ctacte_dia_ant'], 50.0)

        self.assertEqual(data['grand_total']['contado'], move1.amount_total)
        self.assertEqual(data['grand_total']['cta_cte_nd'], move2.amount_total)
        self.assertEqual(data['grand_total']['dev_ctacte_dia_ant'], 50.0)

    def test_compute_data_filters_by_date(self):
        # A move posted for today must not leak into yesterday's report;
        # with no moves/payments on that other date, _compute_data raises.
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0)
        move.action_post()
        yesterday = fields.Date.subtract(self.today, days=1)
        with self.assertRaises(Exception):
            self.report_model._compute_data(yesterday, self.env.company)

    def test_compute_data_raises_when_empty(self):
        far_future = fields.Date.add(self.today, years=50)
        with self.assertRaises(Exception):
            self.report_model._compute_data(far_future, self.env.company)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `_compute_data` not defined.

- [ ] **Step 3: Write minimal implementation**

Add imports and method to `report_cash_closure_vendor.py` (update the top import line too):

```python
from odoo import models, _
from odoo.exceptions import UserError
```

```python
    def _compute_data(self, date, company):
        company = company or self.env.company
        moves = self.env['account.move'].search([
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('invoice_date', '=', date),
            ('company_id', '=', company.id),
        ], order='name asc')
        payments = self.env['account.payment'].search([
            ('partner_type', '=', 'customer'),
            ('payment_type', '=', 'inbound'),
            ('state', 'not in', ('draft', 'cancel')),
            ('date', '=', date),
            ('company_id', '=', company.id),
        ], order='name asc')

        if not moves and not payments:
            raise UserError(_('No se encontraron comprobantes ni cobranzas para el %s.') % date)

        groups = {}
        for move in moves:
            vendor_key, vendor_name, row = self._build_move_row(move)
            group = groups.setdefault(vendor_key, {'name': vendor_name, 'rows': []})
            group['rows'].append(row)
        for payment in payments:
            vendor_key, vendor_name, row = self._build_payment_row(payment)
            group = groups.setdefault(vendor_key, {'name': vendor_name, 'rows': []})
            group['rows'].append(row)

        group_list = []
        for key, group in groups.items():
            subtotal = {col: sum(r[col] for r in group['rows']) for col in SUBTOTAL_KEYS}
            group_list.append({
                'salesperson_name': group['name'],
                'is_unassigned': key == (False, False),
                'rows': group['rows'],
                'subtotal': subtotal,
            })
        group_list.sort(key=lambda g: (g['is_unassigned'], g['salesperson_name']))

        grand_total = {col: sum(g['subtotal'][col] for g in group_list) for col in SUBTOTAL_KEYS}

        return {
            'date': date,
            'company': company,
            'currency': company.currency_id,
            'groups': group_list,
            'grand_total': grand_total,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 20 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/report/report_cash_closure_vendor.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): aggregate moves and payments into vendor groups with totals"
```

---

### Task 8: PDF report (QWeb template + ir.actions.report + paperformat)

**Files:**
- Modify: `sale_vendor_cash_closure/report/report_cash_closure_vendor.py`
- Create: `sale_vendor_cash_closure/report/report_cash_closure_vendor.xml`
- Create: `sale_vendor_cash_closure/views/report_cash_closure_vendor_template.xml`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

This task also creates `cash.closure.report.wizard` model as a bare stub (fields only, no action methods yet) since the report's `_get_report_values` needs to browse it. The wizard's action methods are completed in Task 9.

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_get_report_values_renders_html(self):
        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0)
        move.action_post()
        wizard = self.env['cash.closure.report.wizard'].create({
            'date': self.today,
            'company_id': self.env.company.id,
        })
        values = self.report_model._get_report_values(wizard.ids)
        self.assertIn('groups', values)
        self.assertEqual(values['date'], self.today)

        html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            'sale_vendor_cash_closure.cash_closure_vendor', wizard.ids
        )
        self.assertIn(b'Cierre de Caja', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `cash.closure.report.wizard` model does not exist.

- [ ] **Step 3: Write minimal implementation**

Create the wizard stub (full model, without the two print/export methods yet):

```python
# sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py
from odoo import fields, models


class CashClosureReportWizard(models.TransientModel):
    _name = 'cash.closure.report.wizard'
    _description = 'Vendor Cash Closure Report Wizard'

    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
```

```python
# sale_vendor_cash_closure/wizard/__init__.py
from . import cash_closure_report_wizard
```

Add `_get_report_values` to `ReportCashClosureVendor` in `report_cash_closure_vendor.py`:

```python
    def _get_report_values(self, docids, data=None):
        wizards = self.env['cash.closure.report.wizard'].browse(docids)
        wizard = wizards[:1]
        report_data = self._compute_data(wizard.date, wizard.company_id)
        return {
            'doc_ids': docids,
            'doc_model': 'cash.closure.report.wizard',
            **report_data,
        }
```

Create the report action + landscape paperformat:

```xml
<!-- sale_vendor_cash_closure/report/report_cash_closure_vendor.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <record id="paperformat_cash_closure_vendor" model="report.paperformat">
        <field name="name">Cierre de Caja Vendedor (Apaisado)</field>
        <field name="default" eval="False"/>
        <field name="format">A4</field>
        <field name="orientation">Landscape</field>
        <field name="margin_top">20</field>
        <field name="margin_bottom">20</field>
        <field name="margin_left">7</field>
        <field name="margin_right">7</field>
        <field name="header_line" eval="False"/>
        <field name="header_spacing">20</field>
        <field name="dpi">90</field>
    </record>

    <record id="action_report_cash_closure_vendor" model="ir.actions.report">
        <field name="name">Cierre de Caja por Vendedor</field>
        <field name="model">cash.closure.report.wizard</field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name">sale_vendor_cash_closure.cash_closure_vendor</field>
        <field name="report_file">sale_vendor_cash_closure.cash_closure_vendor</field>
        <field name="paperformat_id" ref="paperformat_cash_closure_vendor"/>
    </record>
</odoo>
```

Create the QWeb template:

```xml
<!-- sale_vendor_cash_closure/views/report_cash_closure_vendor_template.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<odoo>
    <template id="cash_closure_vendor">
        <t t-call="web.html_container">
            <t t-call="web.external_layout">
                <div class="page">
                    <div class="row mb-4">
                        <div class="col-12 text-center">
                            <h2>Cierre de Caja</h2>
                            <h4 t-esc="date"/>
                        </div>
                    </div>

                    <t t-foreach="groups" t-as="group">
                        <div class="row mb-2">
                            <div class="col-12">
                                <h5 class="border-bottom pb-1">
                                    Vendedor: <t t-esc="group['salesperson_name']"/>
                                </h5>
                                <table class="table table-sm">
                                    <thead>
                                        <tr>
                                            <th>Comprobante</th>
                                            <th>Cliente</th>
                                            <th class="text-end">Contado</th>
                                            <th class="text-end">Cta.Cte/ND</th>
                                            <th class="text-end">N/C Cont.</th>
                                            <th class="text-end">Dev.CtaCte D/Ant</th>
                                            <th class="text-end">N/C Dev.CtaCte del Día</th>
                                            <th class="text-end">Fact. MiPyme</th>
                                            <th class="text-end">N/C MiPyme</th>
                                            <th class="text-end">% Desc</th>
                                            <th class="text-end">Desct.</th>
                                            <th class="text-end">Cantid. CC</th>
                                            <th>Lista</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <t t-foreach="group['rows']" t-as="row">
                                            <tr>
                                                <td><t t-esc="row['number']"/></td>
                                                <td><t t-esc="row['partner_name']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['contado']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['cta_cte_nd']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['nc_contado']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['dev_ctacte_dia_ant']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['nc_dev_ctacte_dia']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['fact_mipyme']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['nc_mipyme']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['pct_desc']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['desct']"/></td>
                                                <td class="text-end"><t t-esc="'%.2f' % row['cantidad_cc']"/></td>
                                                <td><t t-esc="row['lista']"/></td>
                                            </tr>
                                        </t>
                                    </tbody>
                                    <tfoot>
                                        <tr class="fw-bold">
                                            <td>Subtotal</td>
                                            <td/>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['contado']"/></td>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['cta_cte_nd']"/></td>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['nc_contado']"/></td>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['dev_ctacte_dia_ant']"/></td>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['nc_dev_ctacte_dia']"/></td>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['fact_mipyme']"/></td>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['nc_mipyme']"/></td>
                                            <td/>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['desct']"/></td>
                                            <td class="text-end"><t t-esc="'%.2f' % group['subtotal']['cantidad_cc']"/></td>
                                            <td/>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                        </div>
                    </t>

                    <div class="row">
                        <div class="col-12 text-end">
                            <h5>Total General</h5>
                            <table class="table table-sm" style="max-width: 500px; margin-left: auto;">
                                <tbody>
                                    <tr><td>Contado</td><td class="text-end"><t t-esc="'%.2f' % grand_total['contado']"/></td></tr>
                                    <tr><td>Cta.Cte/ND</td><td class="text-end"><t t-esc="'%.2f' % grand_total['cta_cte_nd']"/></td></tr>
                                    <tr><td>N/C Cont.</td><td class="text-end"><t t-esc="'%.2f' % grand_total['nc_contado']"/></td></tr>
                                    <tr><td>Dev.CtaCte D/Ant</td><td class="text-end"><t t-esc="'%.2f' % grand_total['dev_ctacte_dia_ant']"/></td></tr>
                                    <tr><td>N/C Dev.CtaCte del Día</td><td class="text-end"><t t-esc="'%.2f' % grand_total['nc_dev_ctacte_dia']"/></td></tr>
                                    <tr><td>Fact. MiPyme</td><td class="text-end"><t t-esc="'%.2f' % grand_total['fact_mipyme']"/></td></tr>
                                    <tr><td>N/C MiPyme</td><td class="text-end"><t t-esc="'%.2f' % grand_total['nc_mipyme']"/></td></tr>
                                    <tr><td>Desct.</td><td class="text-end"><t t-esc="'%.2f' % grand_total['desct']"/></td></tr>
                                    <tr class="fw-bold"><td>Cantid. CC</td><td class="text-end"><t t-esc="'%.2f' % grand_total['cantidad_cc']"/></td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </t>
        </t>
    </template>
</odoo>
```

Register the two new XML files in the manifest's `data` list:

```python
    'data': [
        'security/ir.model.access.csv',
        'report/report_cash_closure_vendor.xml',
        'views/report_cash_closure_vendor_template.xml',
    ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 21 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/report/report_cash_closure_vendor.py sale_vendor_cash_closure/report/report_cash_closure_vendor.xml sale_vendor_cash_closure/views/report_cash_closure_vendor_template.xml sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py sale_vendor_cash_closure/wizard/__init__.py sale_vendor_cash_closure/tests/test_cash_closure_report.py sale_vendor_cash_closure/__manifest__.py
git commit -m "feat(sale_vendor_cash_closure): PDF report template, action and landscape paperformat"
```

---

### Task 9: Wizard actions (PDF button + menu)

**Files:**
- Modify: `sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py`
- Create: `sale_vendor_cash_closure/wizard/cash_closure_report_wizard_views.xml`
- Modify: `sale_vendor_cash_closure/__manifest__.py`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_wizard_action_print_pdf_returns_report_action(self):
        wizard = self.env['cash.closure.report.wizard'].create({
            'date': self.today,
            'company_id': self.env.company.id,
        })
        action = wizard.action_print_pdf()
        self.assertEqual(action['report_name'], 'sale_vendor_cash_closure.cash_closure_vendor')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `action_print_pdf` not defined.

- [ ] **Step 3: Write minimal implementation**

Update `cash_closure_report_wizard.py`:

```python
# sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py
from odoo import fields, models


class CashClosureReportWizard(models.TransientModel):
    _name = 'cash.closure.report.wizard'
    _description = 'Vendor Cash Closure Report Wizard'

    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('sale_vendor_cash_closure.action_report_cash_closure_vendor').report_action(self)
```

Create the wizard view + window action + menu:

```xml
<!-- sale_vendor_cash_closure/wizard/cash_closure_report_wizard_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_cash_closure_report_wizard_form" model="ir.ui.view">
        <field name="name">cash.closure.report.wizard.form</field>
        <field name="model">cash.closure.report.wizard</field>
        <field name="arch" type="xml">
            <form string="Cierre de Caja por Vendedor">
                <group>
                    <field name="date"/>
                    <field name="company_id" groups="base.group_multi_company"/>
                </group>
                <footer>
                    <button name="action_print_pdf" string="Descargar PDF" type="object" class="btn-primary"/>
                    <button name="action_export_xlsx" string="Descargar Excel" type="object" class="btn-primary"/>
                    <button string="Cancelar" class="btn-secondary" special="cancel"/>
                </footer>
            </form>
        </field>
    </record>

    <record id="action_cash_closure_report_wizard" model="ir.actions.act_window">
        <field name="name">Cierre de Caja por Vendedor</field>
        <field name="res_model">cash.closure.report.wizard</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
    </record>

    <menuitem id="menu_cash_closure_report_wizard"
              name="Cierre de Caja por Vendedor"
              action="action_cash_closure_report_wizard"
              parent="account.menu_finance_reports"
              sequence="30"/>
</odoo>
```

Register the new wizard view file in the manifest's `data` list:

```python
    'data': [
        'security/ir.model.access.csv',
        'report/report_cash_closure_vendor.xml',
        'views/report_cash_closure_vendor_template.xml',
        'wizard/cash_closure_report_wizard_views.xml',
    ],
```

Note: `action_export_xlsx` is referenced by the view but implemented in Task 10 — the button will exist but the method comes next. This is fine for module loading (Odoo doesn't validate button targets at XML-load time), but don't click "Descargar Excel" in the UI until Task 10 lands.

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 22 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py sale_vendor_cash_closure/wizard/cash_closure_report_wizard_views.xml sale_vendor_cash_closure/__manifest__.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): wizard PDF action, form view and Accounting menu entry"
```

---

### Task 10: XLSX export

**Files:**
- Modify: `sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py`
- Modify: `sale_vendor_cash_closure/tests/test_cash_closure_report.py`

- [ ] **Step 1: Write the failing test**

Add to `TestCashClosureReport`:

```python
    def test_wizard_action_export_xlsx_creates_readable_attachment(self):
        import base64
        import io
        from openpyxl import load_workbook

        move = self._create_move(self.partner_contado, doc_type=self.doc_type_normal, price_unit=100.0)
        move.invoice_user_id = self.env.user
        move.action_post()

        wizard = self.env['cash.closure.report.wizard'].create({
            'date': self.today,
            'company_id': self.env.company.id,
        })
        action = wizard.action_export_xlsx()
        self.assertEqual(action['type'], 'ir.actions.act_url')

        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'cash.closure.report.wizard'),
            ('res_id', '=', wizard.id),
        ], limit=1, order='id desc')
        self.assertTrue(attachment)

        workbook = load_workbook(io.BytesIO(base64.b64decode(attachment.datas)))
        sheet = workbook.active
        header_row = [cell.value for cell in sheet[1]]
        self.assertEqual(header_row[0], 'Comprobante')
        self.assertEqual(header_row[2], 'Contado')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: FAIL — `action_export_xlsx` not defined.

- [ ] **Step 3: Write minimal implementation**

Update `cash_closure_report_wizard.py` — add imports, the `COLUMN_SPECS`/`SUBTOTAL_KEYS` import, and the export method:

```python
# sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py
import base64
import io

import xlsxwriter

from odoo import fields, models

from ..report.report_cash_closure_vendor import COLUMN_SPECS, SUBTOTAL_KEYS


class CashClosureReportWizard(models.TransientModel):
    _name = 'cash.closure.report.wizard'
    _description = 'Vendor Cash Closure Report Wizard'

    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('sale_vendor_cash_closure.action_report_cash_closure_vendor').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        report_data = self.env['report.sale_vendor_cash_closure.cash_closure_vendor']._compute_data(
            self.date, self.company_id
        )
        return self._build_xlsx_attachment(report_data)

    def _build_xlsx_attachment(self, report_data):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Cierre de Caja')

        fmt_header = workbook.add_format({'bold': True, 'bg_color': '#1F4E79', 'font_color': '#FFFFFF', 'border': 1})
        fmt_group = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2'})
        fmt_subtotal = workbook.add_format({'bold': True, 'top': 1})
        fmt_number = workbook.add_format({'num_format': '#,##0.00'})
        fmt_subtotal_number = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'top': 1})

        col_count = len(COLUMN_SPECS)
        for col, (_key, label) in enumerate(COLUMN_SPECS):
            worksheet.write(0, col, label, fmt_header)
            worksheet.set_column(col, col, 16)

        row_idx = 1
        for group in report_data['groups']:
            worksheet.merge_range(
                row_idx, 0, row_idx, col_count - 1,
                "Vendedor: %s" % group['salesperson_name'], fmt_group,
            )
            row_idx += 1
            for row in group['rows']:
                for col, (key, _label) in enumerate(COLUMN_SPECS):
                    value = row[key]
                    if key in SUBTOTAL_KEYS or key == 'pct_desc':
                        worksheet.write_number(row_idx, col, value, fmt_number)
                    else:
                        worksheet.write(row_idx, col, value or '')
                row_idx += 1

            worksheet.write(row_idx, 0, 'Subtotal', fmt_subtotal)
            worksheet.write_blank(row_idx, 1, None, fmt_subtotal)
            for col, (key, _label) in enumerate(COLUMN_SPECS):
                if col < 2:
                    continue
                if key in SUBTOTAL_KEYS:
                    worksheet.write_number(row_idx, col, group['subtotal'].get(key, 0.0), fmt_subtotal_number)
                else:
                    worksheet.write_blank(row_idx, col, None, fmt_subtotal)
            row_idx += 2

        worksheet.write(row_idx, 0, 'Total General', fmt_subtotal)
        worksheet.write_blank(row_idx, 1, None, fmt_subtotal)
        for col, (key, _label) in enumerate(COLUMN_SPECS):
            if col < 2:
                continue
            if key in SUBTOTAL_KEYS:
                worksheet.write_number(row_idx, col, report_data['grand_total'].get(key, 0.0), fmt_subtotal_number)
            else:
                worksheet.write_blank(row_idx, col, None, fmt_subtotal)

        workbook.close()
        output.seek(0)
        file_data = base64.b64encode(output.read())

        filename = "cierre_caja_%s.xlsx" % self.date
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': file_data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `odoo-bin -d odoo19_dev -u sale_vendor_cash_closure --test-enable --stop-after-init --log-level=test`
Expected: PASS — 23 tests green.

- [ ] **Step 5: Commit**

```bash
git add sale_vendor_cash_closure/wizard/cash_closure_report_wizard.py sale_vendor_cash_closure/tests/test_cash_closure_report.py
git commit -m "feat(sale_vendor_cash_closure): XLSX export sharing the PDF's aggregated data"
```

---

### Task 11: i18n scaffolding

**Files:**
- Create: `sale_vendor_cash_closure/i18n/es.po`
- Create: `sale_vendor_cash_closure/i18n/es_AR.po`

All user-facing strings in this module are already written in Spanish directly in the views/templates (matching this repo's established pattern for Argentine-facing modules), so there's no English-to-Spanish string translation needed here. Per the repo convention of always shipping `es.po`/`es_AR.po` stubs, create the standard empty headers so the module is translation-ready for future field/help-text additions.

- [ ] **Step 1: Create `es.po`**

```po
# Translation of Odoo Server.
# This file contains the translation of the following modules:
# 	* sale_vendor_cash_closure
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Server 19.0\n"
"Report-Msgid-Bugs-To: \n"
"Last-Translator: \n"
"Language-Team: \n"
"Language: es\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: \n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"
```

- [ ] **Step 2: Create `es_AR.po`**

```po
# Translation of Odoo Server.
# This file contains the translation of the following modules:
# 	* sale_vendor_cash_closure
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Server 19.0\n"
"Report-Msgid-Bugs-To: \n"
"Last-Translator: \n"
"Language-Team: \n"
"Language: es_AR\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: \n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"
```

- [ ] **Step 3: Commit**

```bash
git add sale_vendor_cash_closure/i18n/es.po sale_vendor_cash_closure/i18n/es_AR.po
git commit -m "chore(sale_vendor_cash_closure): add i18n stub files"
```

---

### Task 12: Manual end-to-end verification

**Files:** none (manual QA against a real Odoo 19 dev instance)

- [ ] **Step 1: Install the module**

In a dev Odoo 19 instance with Argentine localization (`l10n_ar`) installed and at least one customer invoice/credit note/payment dated today: Apps → Update Apps List → search "Vendor Cash Closure Report" → Install.

- [ ] **Step 2: Confirm the two known-risk fields resolved correctly**

Settings → Technical → Database Structure → Models → search `res.partner` → confirm a boolean field matching "credit limit" exists and matches what Task 2 used (`use_partner_credit_limit`). Do the same for `l10n_latam.document.type` → confirm the FCE codes (201/206/211/202/207/212/203/208/213) match real records in **Accounting → Configuration → Document Types**. Fix the constants in `report_cash_closure_vendor.py` if they diverge, re-run the Task 2 test suite, and commit the fix.

- [ ] **Step 3: Generate the PDF**

Accounting → Reporting → "Cierre de Caja por Vendedor" → pick today's date → "Descargar PDF". Verify: groups appear per salesperson, "Sin vendedor" group (if any) is last, subtotals match the sum of their rows, and the Total General table at the bottom matches the sum of all subtotals.

- [ ] **Step 4: Generate the XLSX**

Same wizard → "Descargar Excel". Open in Excel/LibreOffice: verify header row, per-vendor "Vendedor: X" merged rows, subtotal rows (bold, top border), and the final "Total General" row. Cross-check a couple of amounts against the PDF.

- [ ] **Step 5: Confirm counter_salesperson_id integration (if `pos_centralized_payment` is installed)**

If the target instance also has `pos_centralized_payment` (from the `pos_enhancements` repo) installed, create a POS order with a counter salesperson set, pay it and generate its invoice, then confirm that invoice's row in this report is grouped under the counter salesperson's name (not the cashier/`invoice_user_id`).

- [ ] **Step 6: Report back**

Note any discrepancies found in Steps 2–5 as follow-up commits (fixing the affected task's code + test), or confirm everything matches and the feature is ready for the client.
