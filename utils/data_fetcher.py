"""Data fetching layer for the Streamlit dashboard.

Responsable de:
- Descargar todos los pools de DeFiLlama (con cache de Streamlit).
- Filtrar por protocolo Aura Finance + chain Base.
- Clasificar cada pool como Stable / Semi-stable / Volatile.
- Descargar el histórico de APY/TVL para un pool concreto.

Todas las funciones son puras (reciben/devuelven estructuras estándar de
Python y pandas) salvo las decoradas con `@st.cache_data`, que memoizan
resultados por 5 minutos para evitar golpear la API en cada interacción.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

# Endpoint canónico de yields (el prompt menciona api.llama.fi/yields/pools;
# ambas rutas enrutan al mismo backend, usamos la canónica por estabilidad).
DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
DEFILLAMA_CHART_URL = "https://yields.llama.fi/chart/{pool_id}"

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2

#: Conjunto de tokens considerados "stablecoins" para la clasificación
#: por symbol. Ampliable sin tocar el resto del código.
STABLE_TOKENS: set[str] = {
    # USD majors
    "USDC", "USDT", "DAI", "USDBC", "USDT0", "PYUSD", "FDUSD", "TUSD", "BUSD",
    # CDP / algorítmicas / synthetic
    "GHO", "CRVUSD", "LUSD", "FRAX", "MIM", "USDE", "SUSDE", "USDS", "USDM",
    "USDY", "MKUSD", "USDX", "SUSD", "DOLA", "RAI", "USDP", "GUSD", "USDZ",
    # EUR
    "EURC", "EURS", "AGEUR", "EURA", "EURT",
    # Aave-wrapped (aTokens)
    "AUSDC", "AUSDT", "ADAI", "AGHO", "AUSDBC",
    # Compound-wrapped
    "CUSDC", "CUSDT", "CDAI",
    # Misc
    "USD+", "USDPLUS",
}

# --------------------------------------------------------------------------- #
# Fetch primitives
# --------------------------------------------------------------------------- #

def _get_json(url: str, *, timeout: int = REQUEST_TIMEOUT) -> dict[str, Any]:
    """GET con reintentos + backoff exponencial. Lanza RuntimeError si falla."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AuraYieldTracker/1.0 (+streamlit)",
                },
            )
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * attempt * 3
                logger.warning("429 rate limit, esperando %ds", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            logger.warning("Intento %d/%d falló (%s): %s",
                           attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
    raise RuntimeError(f"Fallaron {MAX_RETRIES} intentos: {last_exc!r}")


@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_pools() -> list[dict[str, Any]]:
    """Descarga el catálogo completo de pools de DeFiLlama (cache 5 min)."""
    payload = _get_json(DEFILLAMA_POOLS_URL)
    pools = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(pools, list):
        raise RuntimeError("Respuesta de DeFiLlama con formato inesperado.")
    logger.info("DeFiLlama devolvió %d pools", len(pools))
    return pools


@st.cache_data(ttl=300, show_spinner=False)
def fetch_pool_chart(pool_id: str) -> pd.DataFrame:
    """Descarga el histórico de APY/TVL de un pool (cache 5 min).

    Returns:
        DataFrame con columnas: ``timestamp`` (datetime64[UTC]),
        ``apy``, ``apyBase``, ``apyReward``, ``tvlUsd``. Devuelve DataFrame
        vacío si el endpoint no tiene datos.
    """
    if not pool_id:
        return pd.DataFrame()
    url = DEFILLAMA_CHART_URL.format(pool_id=pool_id)
    payload = _get_json(url)
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in ("apy", "apyBase", "apyReward", "tvlUsd"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# --------------------------------------------------------------------------- #
# Clasificación de pools
# --------------------------------------------------------------------------- #

# Regex para extraer tokens individuales de un symbol tipo
# "AAVE-USDC-AAVE-GHO", "50USDC-50BOLD", "rETH/WETH".
_TOKEN_SPLIT_RE = re.compile(r"[-/_\s]+")
_WEIGHT_PREFIX_RE = re.compile(r"^\d+([A-Z].*)$")  # "50USDC" → "USDC"


def _extract_tokens(symbol: str | None) -> list[str]:
    """Parte un symbol en tokens individuales, normalizados a MAYÚSCULAS."""
    if not symbol:
        return []
    tokens: list[str] = []
    for raw in _TOKEN_SPLIT_RE.split(symbol.upper()):
        if not raw:
            continue
        m = _WEIGHT_PREFIX_RE.match(raw)
        tokens.append(m.group(1) if m else raw)
    return tokens


def classify_pool(pool: dict[str, Any]) -> str:
    """Devuelve 'Stable', 'Semi-stable' o 'Volatile'.

    Criterios:
    - **Stable**: DeFiLlama marca ``stablecoin=True`` o **todos** los tokens
      del symbol están en :data:`STABLE_TOKENS`.
    - **Semi-stable**: al menos un token del symbol es stable.
    - **Volatile**: ningún token reconocido como stable.
    """
    symbol = pool.get("symbol") or ""
    tokens = _extract_tokens(symbol)

    is_stable_flag = bool(pool.get("stablecoin", False))
    stable_matches = [t for t in tokens if t in STABLE_TOKENS]

    if is_stable_flag or (tokens and len(stable_matches) == len(tokens)):
        return "Stable"
    if stable_matches:
        return "Semi-stable"
    return "Volatile"


def is_stable_related(pool: dict[str, Any]) -> bool:
    """True si el pool tiene al menos un token stable (incluye semi-stables)."""
    return classify_pool(pool) in {"Stable", "Semi-stable"}


# --------------------------------------------------------------------------- #
# Pipeline Aura + Base + DataFrame
# --------------------------------------------------------------------------- #

def filter_aura_on_chain(
    pools: list[dict[str, Any]],
    chain: str = "Base",
) -> list[dict[str, Any]]:
    """Filtra a pools de project ~= 'aura' en la chain indicada."""
    chain_lower = chain.lower()
    out = [
        p for p in pools
        if isinstance(p.get("project"), str)
        and "aura" in p["project"].lower()
        and isinstance(p.get("chain"), str)
        and p["chain"].lower() == chain_lower
    ]
    logger.info("Filtrado a %d pools de Aura en %s", len(out), chain)
    return out


def pools_to_dataframe(pools: list[dict[str, Any]]) -> pd.DataFrame:
    """Normaliza pools a un DataFrame con columnas tipadas para la UI.

    Columnas: ``Symbol``, ``TVL_USD``, ``APY_Total``, ``APY_Base``,
    ``APY_Reward``, ``Pool_ID``, ``Type``, ``URL``, ``Stablecoin_Flag``.
    Ordenado por APY_Total descendente.
    """
    rows: list[dict[str, Any]] = []
    for p in pools:
        rows.append({
            "Symbol": p.get("symbol"),
            "TVL_USD": p.get("tvlUsd"),
            "APY_Total": p.get("apy"),
            "APY_Base": p.get("apyBase"),
            "APY_Reward": p.get("apyReward"),
            "Pool_ID": p.get("pool"),
            "Type": classify_pool(p),
            "URL": p.get("url") or (
                f"https://app.aura.finance/#/8453/pool/{p.get('pool')}"
                if p.get("pool") else ""
            ),
            "Stablecoin_Flag": bool(p.get("stablecoin", False)),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            "APY_Total", ascending=False, na_position="last"
        ).reset_index(drop=True)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_aura_base_pools(chain: str = "Base") -> pd.DataFrame:
    """One-shot helper usado por la UI: descarga, filtra y tabula."""
    all_pools = fetch_all_pools()
    aura = filter_aura_on_chain(all_pools, chain=chain)
    return pools_to_dataframe(aura)
