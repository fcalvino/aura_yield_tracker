"""Presentation layer: DataFrame construction, console tables, summary, CSV.

Se mantiene desacoplado del fetcher para poder sustituir fácilmente la fuente
de datos (DeFiLlama → subgraph → cache local) sin tocar la capa visual.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from config import TARGET_CHAIN, TVL_WARNING_THRESHOLD_USD

logger = logging.getLogger(__name__)

CSV_COLUMNS: list[str] = [
    "symbol",
    "TVL_USD",
    "APY_Total",
    "APY_Base",
    "APY_Reward",
    "pool_id",
    "url",
]


# --------------------------------------------------------------------------- #
# Construcción del DataFrame
# --------------------------------------------------------------------------- #

def _default_url(pool_id: str | None) -> str:
    if not pool_id:
        return ""
    return f"https://app.aura.finance/#/8453/pool/{pool_id}"  # 8453 = Base chainId


def build_dataframe(pools: list[dict[str, Any]]) -> pd.DataFrame:
    """Normaliza la lista de pools en un DataFrame con las columnas objetivo.

    Ordena por TVL descendente. Mantiene valores NaN donde la API no aporta
    datos (no los convierte a 0 para no mentir en los reportes).
    """
    rows: list[dict[str, Any]] = []
    for pool in pools:
        rows.append({
            "symbol": pool.get("symbol"),
            "TVL_USD": pool.get("tvlUsd"),
            "APY_Total": pool.get("apy"),
            "APY_Base": pool.get("apyBase"),
            "APY_Reward": pool.get("apyReward"),
            "pool_id": pool.get("pool"),
            "url": pool.get("url") or _default_url(pool.get("pool")),
        })

    df = pd.DataFrame(rows, columns=CSV_COLUMNS)
    if not df.empty:
        df = (
            df.sort_values("TVL_USD", ascending=False, na_position="last")
              .reset_index(drop=True)
        )
    return df


# --------------------------------------------------------------------------- #
# Impresión por consola
# --------------------------------------------------------------------------- #

def _format_for_display(df: pd.DataFrame) -> pd.DataFrame:
    display = df.copy()
    display["TVL_USD"] = display["TVL_USD"].apply(
        lambda v: f"${v:,.0f}" if pd.notna(v) else "—"
    )
    for col in ("APY_Total", "APY_Base", "APY_Reward"):
        display[col] = display[col].apply(
            lambda v: f"{v:.2f}%" if pd.notna(v) else "—"
        )
    # Truncar URL para que la tabla quepa
    display["url"] = display["url"].apply(
        lambda u: (u[:57] + "...") if isinstance(u, str) and len(u) > 60 else u
    )
    return display


def print_pools_table(df: pd.DataFrame, highlight_pool_id: str | None = None) -> None:
    """Imprime la tabla de pools en consola. Usa tabulate si está disponible."""
    if df.empty:
        print("(No hay pools para mostrar.)")
        return

    display = _format_for_display(df)

    # Agregar marcador visual al pool objetivo
    if highlight_pool_id:
        display.insert(0, "", ["🎯" if pid == highlight_pool_id else "" for pid in df["pool_id"]])

    try:
        from tabulate import tabulate  # type: ignore
        print(tabulate(display, headers="keys", tablefmt="github", showindex=True))
    except ImportError:
        logger.debug("tabulate no instalado; fallback a pandas.to_string().")
        print(display.to_string(index=True))


# --------------------------------------------------------------------------- #
# Resumen final
# --------------------------------------------------------------------------- #

def _find_rank(df: pd.DataFrame, pool_id: str | None) -> int | None:
    if not pool_id or df.empty or "pool_id" not in df.columns:
        return None
    mask = df["pool_id"] == pool_id
    if not mask.any():
        return None
    return int(df.index[mask][0]) + 1


def print_summary(
    df: pd.DataFrame,
    target: dict[str, Any] | None,
    deposit_usd: float,
    chain: str = TARGET_CHAIN,
) -> None:
    """Imprime el bloque de resumen con el pool objetivo y retornos previos.

    Los cálculos aquí son un *preview* rápido para Fase 1. La calculadora
    formal (compounding mensual, tabla de proyecciones, escenarios) vive en
    Fase 2.
    """
    print()
    print("=" * 78)
    print("RESUMEN".center(78))
    print("=" * 78)
    print(f"Encontrados {len(df)} pools de Aura en {chain}.")

    if target is None:
        print("❌ No se encontró el pool objetivo. "
              "Revisa TARGET_POOL_KEYWORDS en config.py.")
        print("=" * 78)
        return

    symbol = target.get("symbol") or "(sin symbol)"
    tvl = target.get("tvlUsd") or 0.0
    apy = target.get("apy") or 0.0
    apy_base = target.get("apyBase")
    apy_reward = target.get("apyReward")
    pool_id = target.get("pool")
    rank = _find_rank(df, pool_id)

    print(f"🎯 Tu pool: {symbol}")
    print(f"   TVL: ${tvl:,.0f}  |  APY total: {apy:.2f}%"
          + (f"  (base {apy_base:.2f}% + reward {apy_reward:.2f}%)"
             if apy_base is not None and apy_reward is not None else ""))
    if rank is not None:
        print(f"   Posición por TVL: #{rank} de {len(df)}")
    print(f"   pool_id: {pool_id}")
    print(f"   URL: {target.get('url') or _default_url(pool_id)}")

    # Preview de retornos (sin compounding — Fase 2 lo amplía).
    if apy > 0:
        annual = deposit_usd * (apy / 100.0)
        monthly = annual / 12.0
        daily = annual / 365.0
        print()
        print(f"💰 Con ${deposit_usd:,.2f} depositados (APY simple, sin compounding):")
        print(f"   • Retorno anual estimado:  ${annual:,.2f}")
        print(f"   • Retorno mensual:         ${monthly:,.2f}")
        print(f"   • Retorno diario:          ${daily:,.2f}")

    # Warnings
    warnings: list[str] = []
    if apy <= 0:
        warnings.append("APY ≤ 0 — verifica si el pool sigue activo / con rewards.")
    if tvl < TVL_WARNING_THRESHOLD_USD:
        warnings.append(
            f"TVL por debajo de ${TVL_WARNING_THRESHOLD_USD:,.0f} → "
            f"posible riesgo de liquidez / slippage."
        )
    warnings.append(
        "APY es variable: depende de emisiones BAL/AURA, precio y TVL. "
        "Este número puede cambiar día a día."
    )
    warnings.append(
        "Pool stable-stable (USDC/GHO) → Impermanent Loss esperado muy bajo, "
        "pero no cero ante depegs."
    )

    if warnings:
        print()
        print("⚠️  Notas:")
        for w in warnings:
            print(f"   • {w}")
    print("=" * 78)


# --------------------------------------------------------------------------- #
# Persistencia
# --------------------------------------------------------------------------- #

def save_to_csv(df: pd.DataFrame, output_dir: Path, chain: str) -> Path:
    """Guarda el DataFrame en CSV con timestamp en el nombre.

    Formato: ``aura_pools_<chain>_<YYYY-MM-DD_HH-MM>.csv``
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = output_dir / f"aura_pools_{chain.lower()}_{timestamp}.csv"
    df.to_csv(path, index=False)
    logger.info("CSV guardado en %s", path)
    return path
