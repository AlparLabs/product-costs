from . import models


def pre_init_hook(env):
    """Antes de instalar: si Adhoc ya estaba en uso, marca como "propios" la regla
    de las fichas y el margen de los productos que ya tienen valor, para que los
    computados nuevos (regla por proveedor, margen por categoría) no los pisen."""
    cr = env.cr
    cr.execute("""
        ALTER TABLE product_supplierinfo ADD COLUMN IF NOT EXISTS use_own_rule boolean;
        UPDATE product_supplierinfo SET use_own_rule = (replenishment_cost_rule_id IS NOT NULL);
        ALTER TABLE product_template ADD COLUMN IF NOT EXISTS use_own_margin boolean;
        UPDATE product_template SET use_own_margin = (COALESCE(sale_margin, 0) != 0);
    """)
