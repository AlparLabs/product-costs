"""Ranking de empresas para elegir fichas de proveedor: la empresa activa (0), su
matriz (1), la matriz de la matriz (2)... y las fichas globales (sin empresa) al
final."""
from __future__ import annotations


def company_ranks(company) -> dict[int, int]:
    ranks: dict[int, int] = {}
    current = company
    while current and current.id not in ranks:
        ranks[current.id] = len(ranks)
        current = current.parent_id
    return ranks


def seller_rank(seller, ranks: dict[int, int]) -> int:
    """Rank de la ficha: el de su empresa, o global (después de todas)."""
    if not seller.company_id:
        return len(ranks)
    return ranks.get(seller.company_id.id, len(ranks) + 1)
