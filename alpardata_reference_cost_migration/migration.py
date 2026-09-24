"""Migración de alpardata_purchase_reference_cost al costo de reposición de Adhoc.

Cada paso es una función independiente (testeable). `run` los ejecuta en orden.
Ver el runbook en README.md.
"""
from __future__ import annotations

import base64
import csv
import io
import logging

from odoo import fields
from odoo.exceptions import UserError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

OLD_BASES = ('reference_cost', 'replacement_cost')


def check_pricelist_bases(env) -> None:
    """Aborta si hay reglas de lista basadas en el costo de referencia/reposición:
    en Adhoc no existe esa base y no se decide en silencio a qué pasarlas."""
    items = env['product.pricelist.item'].sudo().with_context(active_test=False).search([
        ('base', 'in', OLD_BASES),
    ])
    if items:
        detail = ', '.join(f'{i.pricelist_id.display_name} (id {i.id})' for i in items[:20])
        raise UserError(
            f'Hay {len(items)} reglas de listas de precios con base en el costo de '
            f'referencia o de reposición: {detail}. Cambiales la base antes de migrar.'
        )


def _companies_to_check(env):
    """Empresas donde se compara el costo: las que tienen fichas y sus sucursales;
    si hay fichas globales, todas."""
    env.cr.execute(
        'SELECT DISTINCT company_id FROM product_supplierinfo WHERE reference_cost > 0'
    )
    company_ids = [row[0] for row in env.cr.fetchall()]
    Company = env['res.company'].sudo()
    if None in company_ids:
        return Company.search([])
    return Company.search([('id', 'child_of', company_ids)])


def _templates_with_lists(env):
    env.cr.execute("""
        SELECT DISTINCT product_tmpl_id FROM product_supplierinfo
        WHERE reference_cost > 0 AND product_tmpl_id IS NOT NULL
    """)
    return env['product.template'].sudo().browse([row[0] for row in env.cr.fetchall()])


def snapshot_costs(env) -> dict[tuple[int, int], float]:
    """{(company_id, product_tmpl_id): reference_cost} con el módulo viejo."""
    templates = _templates_with_lists(env)
    snapshot = {}
    for company in _companies_to_check(env):
        costs = templates.with_company(company).mapped('reference_cost')
        for template, cost in zip(templates, costs):
            snapshot[(company.id, template.id)] = cost
    return snapshot


def copy_prices(env) -> int:
    """price = reference_cost, por SQL (sin historial). La fecha de último precio de
    Adhoc toma la fecha de modificación de la ficha."""
    env.cr.execute("""
        UPDATE product_supplierinfo
           SET price = reference_cost,
               last_date_price_updated = write_date
         WHERE reference_cost > 0
    """)
    count = env.cr.rowcount
    env['product.supplierinfo'].invalidate_model(['price', 'last_date_price_updated'])
    _logger.info('Migración: %s fichas con price = reference_cost', count)
    return count


def copy_history(env) -> int:
    """Copia product_supplierinfo_cost_history → product_supplierinfo_price_history."""
    env.cr.execute("""
        INSERT INTO product_supplierinfo_price_history (
            supplierinfo_id, product_tmpl_id, partner_id, company_id, currency_id,
            old_price, new_price, variation_pct, change_date, changed_by, change_reason,
            create_uid, create_date, write_uid, write_date
        )
        SELECT h.supplierinfo_id, h.product_tmpl_id, h.partner_id, h.company_id,
               c.currency_id,
               h.old_reference_cost, h.new_reference_cost,
               CASE WHEN COALESCE(h.old_reference_cost, 0) = 0 THEN 0
                    ELSE (h.new_reference_cost / h.old_reference_cost - 1) * 100 END,
               h.change_date, h.changed_by, h.change_reason,
               h.create_uid, h.create_date, h.write_uid, h.write_date
          FROM product_supplierinfo_cost_history h
          LEFT JOIN res_company c ON c.id = h.company_id
    """)
    count = env.cr.rowcount
    _logger.info('Migración: %s registros de historial copiados', count)
    return count


def set_cost_types(env) -> int:
    """Productos con alguna ficha con precio → tipo "precio del proveedor principal"."""
    env.cr.execute("""
        UPDATE product_template t
           SET replenishment_cost_type = 'supplier_price'
         WHERE EXISTS (
             SELECT 1 FROM product_supplierinfo s
              WHERE s.product_tmpl_id = t.id AND s.price > 0
         )
    """)
    count = env.cr.rowcount
    env['product.template'].invalidate_model(['replenishment_cost_type'])
    _logger.info('Migración: %s productos pasan a supplier_price', count)
    return count


def verify(env, snapshot) -> list[dict]:
    """Compara el costo de reposición nuevo contra la foto previa."""
    precision = env['decimal.precision'].precision_get('Product Price')
    Template = env['product.template'].sudo()
    Company = env['res.company'].sudo()
    by_company: dict[int, list[int]] = {}
    for company_id, template_id in snapshot:
        by_company.setdefault(company_id, []).append(template_id)
    rows = []
    for company_id, template_ids in by_company.items():
        templates = Template.browse(template_ids).with_company(Company.browse(company_id))
        templates.invalidate_recordset()
        for template in templates:
            old = snapshot[(company_id, template.id)]
            new = template.replenishment_cost
            if float_compare(old, new, precision_digits=precision) != 0:
                rows.append({
                    'company_id': company_id,
                    'product_tmpl_id': template.id,
                    'product': template.display_name,
                    'old_cost': old,
                    'new_cost': new,
                    'difference': new - old,
                })
    _logger.info('Migración: %s diferencias de costo', len(rows))
    return rows


def write_report(env, rows):
    """Adjunta el CSV de diferencias a la empresa principal (id más bajo)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[
        'company_id', 'product_tmpl_id', 'product', 'old_cost', 'new_cost', 'difference',
    ])
    writer.writeheader()
    writer.writerows(rows)
    main_company = env['res.company'].sudo().search([], order='id asc', limit=1)
    return env['ir.attachment'].sudo().create({
        'name': f'migracion_costo_referencia_{fields.Date.today()}.csv',
        'datas': base64.b64encode(buffer.getvalue().encode('utf-8')),
        'res_model': 'res.company',
        'res_id': main_company.id,
        'mimetype': 'text/csv',
    })


def run(env) -> None:
    check_pricelist_bases(env)
    snapshot = snapshot_costs(env)
    copy_prices(env)
    copy_history(env)
    set_cost_types(env)
    rows = verify(env, snapshot)
    attachment = write_report(env, rows)
    _logger.warning(
        'Migración costo de referencia → Adhoc terminada: %s diferencias. '
        'CSV adjunto id %s en la empresa principal.', len(rows), attachment.id,
    )
