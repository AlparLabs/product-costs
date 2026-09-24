{
    'name': 'AlparData - Costo de Reposición (extensión Adhoc)',
    'version': '19.0.1.0.0',
    'summary': 'Vigencias por fecha, jerarquía de empresas, regla por proveedor, margen por categoría e historial sobre el costo de reposición de Adhoc',
    'author': 'AlparData',
    'website': 'https://alpardata.com.ar',
    'category': 'Inventory/Purchase',
    'license': 'AGPL-3',
    'depends': [
        'product_replenishment_cost',
        'product_replenishment_cost_stock',
        'product_replenishment_cost_sale_margin',
        'product_planned_price',
    ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'pre_init_hook': 'pre_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
