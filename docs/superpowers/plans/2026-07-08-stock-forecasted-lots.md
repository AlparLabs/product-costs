# Stock Forecasted Lots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `stock_forecasted_lots` module so the native Odoo 19 "Forecasted Report" (opened from a sale order line's availability icon, or from a product's Forecast button) shows an "Available lots" section listing, for the warehouse currently selected in the report, each lot's stock/reserved/available quantity — so a salesperson quoting cable-by-the-meter can see how many meters are left on each coil and offer the customer the full coil.

**Architecture:** A Python override of `stock.forecasted_product_product._get_report_data()` (in `report/stock_forecasted.py`) adds a `lots` key to the report data, built from a `stock.quant` query scoped to lot-tracked products and the warehouse's internal locations. A QWeb/OWL template extension (`static/src/stock_forecasted/forecasted_details.xml`, `t-inherit="stock.ForecastedDetails"`) renders that data as a table appended after the native forecast table — no JavaScript needed, since the `ForecastedDetails` component already passes its whole `docs` object (which will now include `lots`) into the template as `props.docs`.

**Tech Stack:** Odoo 19.0 (Python ORM, QWeb/OWL template inheritance), `stock` module's forecasted report, `stock.quant`/`stock.lot` models.

**Spec:** `docs/superpowers/specs/2026-07-08-stock-forecasted-lots-design.md`

---

## Task 1: Module scaffold

**Files:**
- Create: `stock_forecasted_lots/__init__.py`
- Create: `stock_forecasted_lots/__manifest__.py`
- Create: `stock_forecasted_lots/report/__init__.py`

- [ ] **Step 1: Create the root `__init__.py`**

```python
from . import report
```

- [ ] **Step 2: Create the manifest**

```python
{
    'name': 'Stock Forecasted Lots',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Show available lots (e.g. cable coils) in the stock forecasted report',
    'description': """
        Adds an "Available lots" section to the stock Forecasted Report
        (the one opened from a sale order line's availability icon or a
        product's Forecast button). Lists, for the warehouse selected in
        the report, each lot's on-hand, reserved, and available quantity —
        so a salesperson can see how much stock remains on a given lot
        (e.g. meters left on a cable coil) and offer the customer the
        remaining quantity to close out the lot.
    """,
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'license': 'LGPL-3',
    'depends': ['sale_stock'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
```

- [ ] **Step 3: Create the report package `__init__.py`**

```python
from . import stock_forecasted
```

- [ ] **Step 4: Commit**

```bash
git add stock_forecasted_lots/__init__.py stock_forecasted_lots/__manifest__.py stock_forecasted_lots/report/__init__.py
git commit -m "feat(stock_forecasted_lots): scaffold module"
```

---

## Task 2: Report data override — lots for a single warehouse, ordered by availability

**Files:**
- Create: `stock_forecasted_lots/report/stock_forecasted.py`
- Test: `stock_forecasted_lots/tests/__init__.py`
- Test: `stock_forecasted_lots/tests/test_forecasted_lots.py`

This task adds the core behavior: two lots of the same lot-tracked product, no reservations, and asserting they come back sorted with the lowest-availability lot first.

- [ ] **Step 1: Create the tests package `__init__.py`**

```python
from . import test_forecasted_lots
```

- [ ] **Step 2: Write the failing test**

Create `stock_forecasted_lots/tests/test_forecasted_lots.py`:

```python
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestForecastedLots(TransactionCase):

    def setUp(self):
        super().setUp()
        self.warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.stock_location = self.warehouse.lot_stock_id
        self.product = self.env['product.product'].create({
            'name': 'Cable 2mm',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'lot',
        })
        self.lot_a = self.env['stock.lot'].create({
            'name': 'BOBINA-A',
            'product_id': self.product.id,
        })
        self.lot_b = self.env['stock.lot'].create({
            'name': 'BOBINA-B',
            'product_id': self.product.id,
        })
        self.report_model = self.env['stock.forecasted_product_product']

    def test_lots_ordered_by_available_quantity_ascending(self):
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, 100.0, lot_id=self.lot_a)
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, 30.0, lot_id=self.lot_b)

        data = self.report_model.with_context(
            warehouse_id=self.warehouse.id
        )._get_report_data(product_ids=self.product.ids)

        self.assertEqual(len(data['lots']), 2)
        self.assertEqual(data['lots'][0]['id'], self.lot_b.id)
        self.assertEqual(data['lots'][0]['available_quantity'], 30.0)
        self.assertEqual(data['lots'][1]['id'], self.lot_a.id)
        self.assertEqual(data['lots'][1]['available_quantity'], 100.0)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags TestForecastedLots`

Expected: FAIL — `KeyError: 'lots'` (the key doesn't exist yet in the report data), since `stock_forecasted_lots/report/stock_forecasted.py` doesn't exist yet.

- [ ] **Step 4: Write the implementation**

Create `stock_forecasted_lots/report/stock_forecasted.py`:

```python
from odoo import models


class StockForecastedProductProduct(models.AbstractModel):
    _inherit = 'stock.forecasted_product_product'

    def _get_report_data(self, product_template_ids=False, product_ids=False):
        res = super()._get_report_data(
            product_template_ids=product_template_ids, product_ids=product_ids)
        warehouse = self._get_warehouse()
        res['lots'] = self._get_lots_data(product_template_ids, product_ids, warehouse)
        return res

    def _get_lot_tracked_products(self, product_template_ids, product_ids):
        if product_template_ids:
            products = self.env['product.product'].search([
                ('product_tmpl_id', 'in', product_template_ids),
            ])
        else:
            products = self.env['product.product'].browse(product_ids)
        return products.filtered(lambda p: p.tracking == 'lot')

    def _get_lots_data(self, product_template_ids, product_ids, warehouse):
        products = self._get_lot_tracked_products(product_template_ids, product_ids)
        if not products:
            return []

        quants = self.env['stock.quant'].search([
            ('product_id', 'in', products.ids),
            ('lot_id', '!=', False),
            ('location_id', 'child_of', warehouse.view_location_id.id),
            ('location_id.usage', '=', 'internal'),
        ])

        lots_by_id = {}
        for quant in quants:
            entry = lots_by_id.setdefault(quant.lot_id.id, {
                'id': quant.lot_id.id,
                'display_name': quant.lot_id.display_name,
                'product_display_name': quant.product_id.display_name,
                'quantity': 0.0,
                'reserved_quantity': 0.0,
                'uom': quant.product_uom_id.name,
            })
            entry['quantity'] += quant.quantity
            entry['reserved_quantity'] += quant.reserved_quantity

        lots = []
        for entry in lots_by_id.values():
            entry['available_quantity'] = entry['quantity'] - entry['reserved_quantity']
            if entry['quantity'] or entry['available_quantity']:
                lots.append(entry)
        lots.sort(key=lambda lot: lot['available_quantity'])
        return lots
```

- [ ] **Step 5: Run test to verify it passes**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags TestForecastedLots`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add stock_forecasted_lots/report/stock_forecasted.py stock_forecasted_lots/tests/__init__.py stock_forecasted_lots/tests/test_forecasted_lots.py
git commit -m "feat(stock_forecasted_lots): add lots to forecasted report data, ordered by availability"
```

---

## Task 3: Filter by the report's warehouse

**Files:**
- Modify: `stock_forecasted_lots/tests/test_forecasted_lots.py`

Verifies that a lot with stock in a *different* warehouse than the one selected in the report does not show up.

- [ ] **Step 1: Write the failing test**

Add to `TestForecastedLots` in `stock_forecasted_lots/tests/test_forecasted_lots.py`:

```python
    def test_lots_filtered_by_warehouse(self):
        other_warehouse = self.env['stock.warehouse'].create({
            'name': 'Depot Test',
            'code': 'DEPT',
        })
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, 100.0, lot_id=self.lot_a)
        self.env['stock.quant']._update_available_quantity(
            self.product, other_warehouse.lot_stock_id, 50.0, lot_id=self.lot_b)

        data = self.report_model.with_context(
            warehouse_id=self.warehouse.id
        )._get_report_data(product_ids=self.product.ids)

        self.assertEqual([lot['id'] for lot in data['lots']], [self.lot_a.id])
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags TestForecastedLots`

Expected: PASS already — the implementation from Task 2 scopes the quant search to `warehouse.view_location_id` via `child_of`, so this test should pass without further code changes. This step confirms that behavior with an explicit regression test rather than leaving it unverified.

- [ ] **Step 3: Commit**

```bash
git add stock_forecasted_lots/tests/test_forecasted_lots.py
git commit -m "test(stock_forecasted_lots): verify lots are scoped to the report's warehouse"
```

---

## Task 4: Exclude non-lot-tracked products and empty lots

**Files:**
- Modify: `stock_forecasted_lots/tests/test_forecasted_lots.py`

- [ ] **Step 1: Write the tests**

Add to `TestForecastedLots`:

```python
    def test_product_without_lot_tracking_returns_no_lots(self):
        untracked_product = self.env['product.product'].create({
            'name': 'Cinta aislante',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'none',
        })
        self.env['stock.quant']._update_available_quantity(
            untracked_product, self.stock_location, 20.0)

        data = self.report_model.with_context(
            warehouse_id=self.warehouse.id
        )._get_report_data(product_ids=untracked_product.ids)

        self.assertEqual(data['lots'], [])

    def test_lot_tracked_product_without_stock_returns_no_lots(self):
        data = self.report_model.with_context(
            warehouse_id=self.warehouse.id
        )._get_report_data(product_ids=self.product.ids)

        self.assertEqual(data['lots'], [])

    def test_lot_depleted_to_zero_is_excluded(self):
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, 10.0, lot_id=self.lot_a)
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, -10.0, lot_id=self.lot_a)

        data = self.report_model.with_context(
            warehouse_id=self.warehouse.id
        )._get_report_data(product_ids=self.product.ids)

        self.assertEqual(data['lots'], [])
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags TestForecastedLots`

Expected: PASS for all three —
- `_get_lot_tracked_products` filters on `tracking == 'lot'`, so an untracked product yields an empty product recordset and `_get_lots_data` short-circuits to `[]`.
- A lot-tracked product with no quants at all makes the `stock.quant` search return an empty recordset, so the loop never populates `lots_by_id` and `[]` is returned.
- Depleting a lot to exactly zero leaves a quant with `quantity == 0` and `reserved_quantity == 0`, so `available_quantity == 0`; the `if entry['quantity'] or entry['available_quantity']` guard excludes it.

- [ ] **Step 3: Commit**

```bash
git add stock_forecasted_lots/tests/test_forecasted_lots.py
git commit -m "test(stock_forecasted_lots): verify untracked, stockless, and depleted lots are excluded"
```

---

## Task 5: Partial reservation reflected in available quantity

**Files:**
- Modify: `stock_forecasted_lots/tests/test_forecasted_lots.py`

- [ ] **Step 1: Write the test**

Add to `TestForecastedLots`:

```python
    def test_partial_reservation_reflected_in_available_quantity(self):
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, 100.0,
            reserved_quantity=30.0, lot_id=self.lot_a)

        data = self.report_model.with_context(
            warehouse_id=self.warehouse.id
        )._get_report_data(product_ids=self.product.ids)

        lot_data = data['lots'][0]
        self.assertEqual(lot_data['quantity'], 100.0)
        self.assertEqual(lot_data['reserved_quantity'], 30.0)
        self.assertEqual(lot_data['available_quantity'], 70.0)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags TestForecastedLots`

Expected: PASS — `available_quantity` is computed as `quantity - reserved_quantity` in `_get_lots_data`.

- [ ] **Step 3: Run the full test file to confirm no regressions**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags TestForecastedLots`

Expected: PASS — all 6 tests green (ordering, warehouse filter, untracked product, stockless lot-tracked product, depleted lot, partial reservation).

- [ ] **Step 4: Commit**

```bash
git add stock_forecasted_lots/tests/test_forecasted_lots.py
git commit -m "test(stock_forecasted_lots): verify reserved quantity reduces available quantity"
```

---

## Task 6: Render the "Available lots" section in the forecast popup

**Files:**
- Create: `stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml`

The native `ForecastedDetails` OWL component (`addons/stock/static/src/stock_forecasted/forecasted_details.js`) declares `static props = { docs: Object, openView: Function, reloadReport: Function }` and its template accesses `props.docs.lines`, `props.docs.multiple_product`, etc. Since `docs` is passed through as a whole object, the `lots` key added in Task 2 is already available in the template as `props.docs.lots` — no JS changes are needed, only a QWeb template extension.

The native template (`addons/stock/static/src/stock_forecasted/forecasted_details.xml`) wraps everything in:
```xml
<t t-name="stock.ForecastedDetails">
    <table class="table table-bordered bg-view o_forecasted_details_table">
        ...
    </table>
</t>
```

- [ ] **Step 1: Create the template extension**

Create `stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<templates id="template" xml:space="preserve">
    <t t-name="stock_forecasted_lots.ForecastedDetailsLots"
       t-inherit="stock.ForecastedDetails"
       t-inherit-mode="extension">
        <xpath expr="//table[hasclass('o_forecasted_details_table')]" position="after">
            <div t-if="props.docs.lots and props.docs.lots.length"
                 class="o_forecasted_lots mt-3">
                <h6>Available lots</h6>
                <table class="table table-sm table-bordered">
                    <thead>
                        <tr>
                            <th>Lot</th>
                            <th t-if="props.docs.multiple_product">Product</th>
                            <th class="text-end">In Stock</th>
                            <th class="text-end">Reserved</th>
                            <th class="text-end">Available</th>
                        </tr>
                    </thead>
                    <tbody>
                        <t t-foreach="props.docs.lots" t-as="lot" t-key="lot.id">
                            <tr>
                                <td><t t-esc="lot.display_name"/></td>
                                <td t-if="props.docs.multiple_product">
                                    <t t-esc="lot.product_display_name"/>
                                </td>
                                <td class="text-end">
                                    <t t-esc="lot.quantity"/> <t t-esc="lot.uom"/>
                                </td>
                                <td class="text-end">
                                    <t t-esc="lot.reserved_quantity"/> <t t-esc="lot.uom"/>
                                </td>
                                <td class="text-end">
                                    <t t-esc="lot.available_quantity"/> <t t-esc="lot.uom"/>
                                </td>
                            </tr>
                        </t>
                    </tbody>
                </table>
            </div>
        </xpath>
    </t>
</templates>
```

- [ ] **Step 2: Manual verification in a running Odoo instance**

This step has no automated test — OWL template rendering in the forecast popup is verified by hand, per the spec's testing section.

1. Start Odoo with the module installed: `odoo-bin -d <dev_db> -i stock_forecasted_lots`
2. Create a storable product with `Tracking: By Lots`.
3. Register two lots for it with different on-hand quantities (e.g. via **Inventory > Physical Inventory** or **Inventory Adjustments**), one of them partially reserved by an outgoing transfer.
4. Open a sale order, add a line for that product, click the availability icon on the line to open **"Availability"** / the forecast report.
5. Confirm the "Available lots" table appears below the native forecast table, listing both lots with correct In Stock / Reserved / Available values, sorted with the lowest-available lot first.
6. Switch the warehouse selector in the report header (if more than one warehouse exists) and confirm the lots list updates to match.
7. Repeat for a product with `Tracking: No Tracking` and confirm the "Available lots" section does not render at all.

- [ ] **Step 3: Commit**

```bash
git add stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml
git commit -m "feat(stock_forecasted_lots): render available lots section in forecast popup"
```

---

## Task 7: Spanish (Argentina) translations

**Files:**
- Create: `stock_forecasted_lots/i18n/es_AR.po`

- [ ] **Step 1: Create the translation file**

Create `stock_forecasted_lots/i18n/es_AR.po`:

```po
# Translation of Odoo Server.
# This file contains the translation of the following modules:
# 	* stock_forecasted_lots
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

#. module: stock_forecasted_lots
#. odoo-javascript
#: code:addons/stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml:0
msgid "Available lots"
msgstr "Lotes disponibles"

#. module: stock_forecasted_lots
#. odoo-javascript
#: code:addons/stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml:0
msgid "Lot"
msgstr "Lote"

#. module: stock_forecasted_lots
#. odoo-javascript
#: code:addons/stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml:0
msgid "Product"
msgstr "Producto"

#. module: stock_forecasted_lots
#. odoo-javascript
#: code:addons/stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml:0
msgid "In Stock"
msgstr "En stock"

#. module: stock_forecasted_lots
#. odoo-javascript
#: code:addons/stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml:0
msgid "Reserved"
msgstr "Reservado"

#. module: stock_forecasted_lots
#. odoo-javascript
#: code:addons/stock_forecasted_lots/static/src/stock_forecasted/forecasted_details.xml:0
msgid "Available"
msgstr "Disponible"
```

- [ ] **Step 2: Register the translation in the manifest**

Modify `stock_forecasted_lots/__manifest__.py` — no `data` entry is needed for `.po` files (Odoo auto-discovers `i18n/*.po`), so this step is just a sanity check: confirm the file lives at `stock_forecasted_lots/i18n/es_AR.po` (already correct from Step 1) and move on.

- [ ] **Step 3: Commit**

```bash
git add stock_forecasted_lots/i18n/es_AR.po
git commit -m "i18n(stock_forecasted_lots): add es_AR translations"
```

---

## Task 8: Full module verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite for the module**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags /stock_forecasted_lots`

Expected: All tests in `stock_forecasted_lots/tests/test_forecasted_lots.py` PASS (6 tests): ordering, warehouse filter, untracked product, stockless lot-tracked product, depleted lot, partial reservation.

- [ ] **Step 2: Confirm the module installs cleanly on a fresh database**

Run: `odoo-bin -d <fresh_test_db> --stop-after-init -i stock_forecasted_lots`

Expected: exits 0, no traceback, no missing-dependency errors (depends only on `sale_stock`, which is already a dependency of every module in this repo's sales extensions).

- [ ] **Step 3: Repeat the manual browser verification from Task 6, Step 2**

This confirms the end-to-end flow once more after all commits: create a lot-tracked product, register two lots, open the forecast report from a sale order line, and visually confirm the "Available lots" table renders correctly and updates when the warehouse changes.

---

## Task 9: Verify lots data via the `stock.forecasted_product_template` model

**Files:**
- Modify: `stock_forecasted_lots/tests/test_forecasted_lots.py`

A whole-feature code review flagged that the module's design spec assumes — but no test ever exercises — that patching `stock.forecasted_product_product._get_report_data` (via plain `_inherit`, no `_name`) also applies to `stock.forecasted_product_template`, since Odoo core defines that model as `_inherit = ['stock.forecasted_product_product']`. This second model backs the "Forecast" button on a product form and is called with `product_template_ids=` instead of `product_ids=`, exercising the other branch of `_get_lot_tracked_products`. All 6 existing tests only ever call the `stock.forecasted_product_product` model with `product_ids=`, so this entry point has zero coverage. This task adds one test to close that gap.

- [ ] **Step 1: Write the test**

Add to `TestForecastedLots` in `stock_forecasted_lots/tests/test_forecasted_lots.py`:

```python
    def test_lots_via_product_template_report_model(self):
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, 100.0, lot_id=self.lot_a)
        self.env['stock.quant']._update_available_quantity(
            self.product, self.stock_location, 30.0, lot_id=self.lot_b)

        data = self.env['stock.forecasted_product_template'].with_context(
            warehouse_id=self.warehouse.id
        )._get_report_data(product_template_ids=self.product.product_tmpl_id.ids)

        self.assertEqual(len(data['lots']), 2)
        self.assertEqual(data['lots'][0]['id'], self.lot_b.id)
        self.assertEqual(data['lots'][0]['available_quantity'], 30.0)
        self.assertEqual(data['lots'][1]['id'], self.lot_a.id)
        self.assertEqual(data['lots'][1]['available_quantity'], 100.0)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `odoo-bin -d <test_db> --test-enable --stop-after-init -i stock_forecasted_lots --test-tags TestForecastedLots`

Expected: PASS — `stock.forecasted_product_template`'s registry-built class inherits `_get_report_data` from the already-patched `stock.forecasted_product_product` class (core declares `_inherit = ['stock.forecasted_product_product']`, no override of this method), so the call resolves to our override and exercises the `product_template_ids` branch of `_get_lot_tracked_products` for the first time.

- [ ] **Step 3: Commit**

```bash
git add stock_forecasted_lots/tests/test_forecasted_lots.py docs/superpowers/plans/2026-07-08-stock-forecasted-lots.md
git commit -m "test(stock_forecasted_lots): verify lots data via the forecasted_product_template model"
```
