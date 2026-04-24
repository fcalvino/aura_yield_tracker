"""AuraYieldTracker - Fase 1: Fetcher básico.

Entry point CLI. Descarga los pools de Aura Finance en Base desde DeFiLlama,
los normaliza en un DataFrame, imprime una tabla, destaca el pool objetivo
USDC-GHO y guarda el resultado en CSV con timestamp.

Uso básico:
    python main.py
    python main.py --deposit 5000 --chain Base --log-level DEBUG
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import (
    DEPOSIT_USD,
    OUTPUT_DIR,
    TARGET_CHAIN,
    TARGET_POOL_KEYWORDS,
)
from fetcher import (
    DataFetchError,
    fetch_defillama_pools,
    filter_pools,
    find_target_pool,
)
from reporter import (
    build_dataframe,
    print_pools_table,
    print_summary,
    save_to_csv,
)


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

def setup_logging(level: str = "INFO") -> None:
    """Configura logging raíz con formato consistente."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aura-yield-tracker",
        description=(
            "Fase 1 — Descarga y reporta pools de Aura Finance en Base "
            "desde DeFiLlama, destacando el pool USDC/GHO."
        ),
    )
    parser.add_argument(
        "--deposit",
        type=float,
        default=DEPOSIT_USD,
        help=f"Depósito en USD para los cálculos (default: {DEPOSIT_USD}).",
    )
    parser.add_argument(
        "--chain",
        type=str,
        default=TARGET_CHAIN,
        help=f"Cadena a filtrar (default: {TARGET_CHAIN}).",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=TARGET_POOL_KEYWORDS,
        help=(
            "Keywords (TODAS requeridas) para identificar el pool objetivo. "
            f"Default: {TARGET_POOL_KEYWORDS}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Directorio de salida para el CSV (default: {OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging (default: INFO).",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="No escribir el CSV (útil para debugging / ejecución rápida).",
    )
    return parser.parse_args(argv)


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #

def run(args: argparse.Namespace) -> int:
    """Ejecuta el pipeline completo. Devuelve un exit code.

    0 = OK
    1 = No hay pools en la chain pedida / pool objetivo no encontrado
    2 = Error de red / API
    """
    logger = logging.getLogger("aura_tracker")

    # 1. Fetch
    try:
        pools_raw = fetch_defillama_pools()
    except DataFetchError as exc:
        logger.error("❌ No se pudo obtener datos de DeFiLlama: %s", exc)
        logger.error("   Fallback al subgraph aún no implementado (Fase 1). "
                     "Reintenta en unos minutos o revisa tu conexión.")
        return 2

    # 2. Filter
    aura_pools = filter_pools(pools_raw, chain=args.chain)
    if not aura_pools:
        logger.warning(
            "No se encontraron pools de Aura en %s. "
            "¿Seguro que la chain está soportada? Prueba con --chain Ethereum.",
            args.chain,
        )
        return 1

    # 3. Tabla normalizada
    df = build_dataframe(aura_pools)

    # 4. Buscar pool objetivo ANTES de imprimir para pasarle el highlight.
    target = find_target_pool(aura_pools, args.keywords)

    print_pools_table(df, highlight_pool_id=(target or {}).get("pool"))
    print_summary(df, target, deposit_usd=args.deposit, chain=args.chain)

    # 5. Persistencia
    if not args.no_csv:
        path = save_to_csv(df, args.output_dir, chain=args.chain)
        print(f"\n💾 CSV guardado en: {path}")

    return 0 if target is not None else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_level)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
