"""AuraYieldTracker • Stables Base
Monitoreo en tiempo real de pools de stablecoins de Aura Finance en Base –
APY, TVL y simulador de compounding.

Versión: 2.0 — production-ready para Streamlit Community Cloud.

Secciones (tabs):
    1. Overview         → métricas + chart histórico del pool seleccionado.
    2. Todos los Pools  → tabla interactiva con filtros de todos los stables.
    3. Simulador        → simulador de compounding mensual.
    4. Histórico        → histórico completo + estadísticas + exports.

Datos vía DeFiLlama Yields API con cache de 5 min (@st.cache_data ttl=300).
Deploy: https://share.streamlit.io — ver README.md para instrucciones.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st

# =========================================================================== #
# Page config  ← DEBE ser la primera llamada a Streamlit
# =========================================================================== #

st.set_page_config(
    layout="wide",
    page_title="AuraYieldTracker • Stables Base",
    page_icon="📈",
    initial_sidebar_state="expanded",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# =========================================================================== #
# Constantes API
# =========================================================================== #

DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
DEFILLAMA_CHART_URL = "https://yields.llama.fi/chart/{pool_id}"
AURA_GRAPHQL_URL    = "https://data.aura.finance/graphql"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2

# === MULTI-CHAIN SUPPORT ===
CHAINS: dict[str, dict] = {
    "Base":     {"id": 8453,  "display_name": "Base"},
    "Ethereum": {"id": 1,     "display_name": "Ethereum"},
    "Arbitrum": {"id": 42161, "display_name": "Arbitrum"},
    "Gnosis":   {"id": 100,   "display_name": "Gnosis"},
}

# Aave market names per chain (for URL construction — DeFiLlama returns url: null)
AAVE_MARKET_NAMES: dict[str, str] = {
    "Ethereum": "proto_mainnet_v3",
    "Base":     "proto_base_v3",
    "Arbitrum": "proto_arbitrum_v3",
    "Gnosis":   "proto_gnosis_v3",
}

# === FIX 4b: Stable tokens ampliado con keywords más robustas ===
STABLE_TOKENS: set[str] = {
    # USD majors
    "USDC", "USDT", "DAI", "USDBC", "USDT0", "PYUSD", "FDUSD", "TUSD", "BUSD",
    # CDP / algorítmicas / synthetic
    "GHO", "CRVUSD", "LUSD", "FRAX", "MIM", "USDE", "SUSDE", "USDS", "USDM",
    "USDY", "MKUSD", "USDX", "SUSD", "DOLA", "RAI", "USDP", "GUSD", "USDZ",
    "BOLD", "USDD", "USDR", "FXUSD", "FRXUSD",
    # EUR / other fiat pegs
    "EURC", "EURS", "AGEUR", "EURA", "EURT", "EURE", "VCHF",
    "XSGD", "NZDS", "BRLA",
    # Aave-wrapped (aTokens)
    "AUSDC", "AUSDT", "ADAI", "AGHO", "AUSDBC",
    # Compound-wrapped
    "CUSDC", "CUSDT", "CDAI",
    # Misc
    "USD+", "USDPLUS",
}

# =========================================================================== #
# Premium dark-theme CSS
# =========================================================================== #

CUSTOM_CSS = """
<style>
#MainMenu, footer, header {visibility: hidden;}
[data-testid="stExpandSidebarButton"] { position: fixed !important; left: 0.5rem !important; top: 0.5rem !important; z-index: 999999 !important; visibility: visible !important; display: flex !important; opacity: 1 !important; pointer-events: all !important; }

.main .block-container {
    padding-top: 0.8rem;
    padding-bottom: 2.5rem;
    max-width: 1600px;
}

/* ── Welcome banner ── */
.welcome-banner {
    background: linear-gradient(135deg, #0d2b20 0%, #0e1117 60%, #1a1d29 100%);
    border: 1px solid #00ff9d44;
    border-left: 4px solid #00ff9d;
    padding: 1.1rem 1.6rem;
    border-radius: 10px;
    margin-bottom: 1.2rem;
}
.welcome-banner h2 { color: #00ff9d; margin: 0 0 0.3rem 0; font-size: 1.35rem; }
.welcome-banner p  { color: #aab4c4; margin: 0; font-size: 0.93rem; line-height: 1.5; }

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1a1d29 0%, #14161f 100%);
    border: 1px solid #2a2f3d;
    padding: 1rem 1.2rem;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.35);
    transition: transform .15s ease, border-color .15s ease;
}
[data-testid="stMetric"]:hover { transform: translateY(-2px); border-color: #00ff9d; }
[data-testid="stMetricLabel"] { color: #8b93a7 !important; font-size: 0.78rem !important; text-transform: uppercase; letter-spacing: 0.6px; }
[data-testid="stMetricValue"] { color: #fafafa !important; font-size: 1.65rem !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"]  { font-size: 0.82rem !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 5px; background-color: #14161f; padding: 5px; border-radius: 10px; margin-bottom: 0.5rem;
}
.stTabs [data-baseweb="tab"] {
    background-color: transparent; color: #8b93a7; border-radius: 8px;
    padding: 9px 16px; font-weight: 500; font-size: 0.92rem;
}
.stTabs [aria-selected="true"] {
    background-color: #00ff9d !important; color: #0e1117 !important; font-weight: 700;
}

/* ── Refresh button (prominent) ── */
.stButton > button[kind="primary"],
div[data-testid="stButton-primary"] > button {
    background: linear-gradient(135deg, #00ff9d 0%, #00c97c 100%) !important;
    color: #0e1117 !important; font-weight: 700 !important;
    border: none !important; border-radius: 8px !important;
    font-size: 1rem !important; padding: 0.55rem 1.4rem !important;
    box-shadow: 0 0 14px rgba(0,255,157,0.3) !important;
}
.stButton > button {
    background: linear-gradient(135deg, #00ff9d 0%, #00d97f 100%);
    color: #0e1117; font-weight: 700; border: none; border-radius: 8px;
    transition: transform .1s ease, box-shadow .1s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0,255,157,0.4);
    color: #0e1117;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #14161f;
    border-right: 1px solid #2a2f3d;
}
[data-testid="stSidebar"] hr { border-color: #2a2f3d; }

/* ── Headings ── */
h1 { color: #fafafa; border-bottom: 2px solid #00ff9d; padding-bottom: 0.35rem; }
h2, h3, h4 { color: #fafafa; }

/* ── Pool highlight card ── */
.pool-card {
    background: linear-gradient(135deg, #1a1d29 0%, #0e1117 100%);
    border-left: 4px solid #00ff9d;
    padding: 0.85rem 1.3rem; border-radius: 8px; margin: 0.2rem 0 1.2rem 0;
}
.pool-card h3 { margin: 0 0 0.3rem 0; color: #00ff9d; font-size: 1.15rem; }
.pool-card .sub { color: #8b93a7; font-size: 0.88rem; }

/* ── Badges ── */
.badge { display: inline-block; padding: 2px 9px; border-radius: 4px; font-weight: 600; font-size: 0.76rem; margin-right: 5px; }
.badge-stable   { background:#00ff9d; color:#0e1117; }
.badge-semi     { background:#ffd700; color:#0e1117; }
.badge-volatile { background:#ff4444; color:#fafafa; }

/* ── Footer ── */
.app-footer {
    text-align: center; color: #555e72; font-size: 0.8rem; margin-top: 1rem;
    padding: 0.8rem 0 0.2rem 0; border-top: 1px solid #2a2f3d;
}
.app-footer a { color: #00ff9d; text-decoration: none; }
.app-footer a:hover { color: #00d97f; }

/* ── Links ── */
a { color: #00ff9d; } a:hover { color: #00d97f; }

/* ── DataFrame ── */
[data-testid="stDataFrame"] { border: 1px solid #2a2f3d; border-radius: 8px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =========================================================================== #
# Session state
# =========================================================================== #

# === FIX DINAMISMO SIMULADOR ===
def _sim_sync_preset() -> None:
    """Cuando cambia el radio Preset APY, sincroniza el slider sim_apy."""
    preset   = st.session_state.get("sim_preset", "Pool actual")
    pool_apy = st.session_state.get("sim_current_pool_apy", 0.0)
    preset_map = {
        "Conservador 4%": 4.0,
        "Base 6.5%":      6.5,
        "Optimista 12%":  12.0,
        "Pool actual":    pool_apy,
    }
    if preset in preset_map:
        st.session_state["sim_apy"] = min(preset_map[preset], 50.0)


def _sim_apy_to_custom() -> None:
    """Cuando el usuario mueve el slider APY, cambia preset a Custom."""
    st.session_state["sim_preset"] = "Custom"


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("deposit_usd", 3240.00)
    ss.setdefault("selected_pool_id", None)
    ss.setdefault("selected_chain", "Base")      # === MULTI-CHAIN SUPPORT ===
    ss.setdefault("selected_protocol", "Aura Finance")
    ss.setdefault("only_stables", True)
    ss.setdefault("pure_stables_only", False)
    # === FIX 1: Auto-refresh state ===
    ss.setdefault("refresh_start", None)
    ss.setdefault("refresh_interval", 15)
    # === FIX DINAMISMO SIMULADOR ===
    ss.setdefault("sim_deposito",         3240.00)
    ss.setdefault("sim_preset",           "")   # se asigna dinámicamente en tab_sim
    ss.setdefault("sim_apy",              6.5)
    ss.setdefault("sim_meses",            12)
    ss.setdefault("sim_current_pool_apy", 0.0)


_init_state()


# Callback: reset selected pool when chain or protocol switches
def _reset_pool_on_chain_change() -> None:
    st.session_state["selected_pool_id"] = None


# =========================================================================== #
# Data-fetch layer (autocontenido, sin imports locales)
# =========================================================================== #

def _get_json(url: str, *, timeout: int = REQUEST_TIMEOUT) -> dict[str, Any]:
    """GET con reintentos + backoff exponencial."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AuraYieldTracker/2.0 (+streamlit-cloud)",
                },
            )
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * attempt * 3
                logger.warning("429 rate-limit; esperando %ds (intento %d)", wait, attempt)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            logger.warning("Intento %d/%d falló (%s): %s", attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * attempt)
    raise RuntimeError(f"Fallaron {MAX_RETRIES} intentos contra {url}: {last_exc!r}")


@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_pools() -> list[dict[str, Any]]:
    """Catálogo completo de DeFiLlama (cache 5 min)."""
    payload = _get_json(DEFILLAMA_POOLS_URL)
    pools = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(pools, list):
        raise RuntimeError("Respuesta de DeFiLlama con formato inesperado.")
    logger.info("DeFiLlama devolvió %d pools", len(pools))
    return pools


@st.cache_data(ttl=300, show_spinner=False)
def fetch_pool_chart(pool_id: str) -> pd.DataFrame:
    """Histórico APY/TVL de un pool concreto (cache 5 min)."""
    if not pool_id:
        return pd.DataFrame()
    url = DEFILLAMA_CHART_URL.format(pool_id=pool_id)
    try:
        payload = _get_json(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error al cargar histórico de %s: %s", pool_id, exc)
        return pd.DataFrame()

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


_TOKEN_SPLIT_RE   = re.compile(r"[-/_\s\.]+")
_WEIGHT_PREFIX_RE = re.compile(r"^\d+([A-Z].*)$")


def _extract_tokens(symbol: str | None) -> list[str]:
    if not symbol:
        return []
    tokens: list[str] = []
    for raw in _TOKEN_SPLIT_RE.split(symbol.upper()):
        if not raw:
            continue
        m = _WEIGHT_PREFIX_RE.match(raw)
        tokens.append(m.group(1) if m else raw)
    return tokens


def build_aave_url(pool: dict[str, Any], chain: str) -> str:
    """Construye la URL de Aave para un pool dado su underlyingToken y chain.

    Args:
        pool: Pool dict de DeFiLlama.
        chain: Nombre de la chain (e.g. "Base", "Ethereum").

    Returns:
        URL de Aave reserve-overview o fallback a markets page.
    """
    market = AAVE_MARKET_NAMES.get(chain, "proto_mainnet_v3")
    underlying = pool.get("underlyingTokens") or []
    if underlying:
        addr = underlying[0].lower()
        return f"https://app.aave.com/reserve-overview/?underlyingAsset={addr}&marketName={market}"
    return "https://app.aave.com/markets/"


def classify_pool(pool: dict[str, Any]) -> str:
    """'Stable' | 'Semi-stable' | 'Volatile'."""
    symbol = pool.get("symbol") or ""
    tokens = _extract_tokens(symbol)
    is_stable_flag = bool(pool.get("stablecoin", False))
    stable_matches = [t for t in tokens if t in STABLE_TOKENS]
    if is_stable_flag or (tokens and len(stable_matches) == len(tokens)):
        return "Stable"
    if stable_matches:
        return "Semi-stable"
    return "Volatile"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_aura_pid_map() -> dict:
    """Builds {(chainId, frozenset_of_token_addrs_lower): poolId} from Aura GraphQL.

    Aura's API returns only Ethereum when called without chainId filter,
    so we query each supported chain explicitly.
    """
    pid_map: dict = {}
    for cid in [c["id"] for c in CHAINS.values()]:
        try:
            resp = requests.post(
                AURA_GRAPHQL_URL,
                json={"query": f"{{pools(chainId:{cid}){{poolId isShutdown tokens{{address}}}}}}"},
                timeout=15,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            pools = resp.json().get("data", {}).get("pools", [])
            active = 0
            for p in pools:
                if p.get("isShutdown"):
                    continue
                pid = p.get("poolId")
                toks = frozenset(t["address"].lower() for t in (p.get("tokens") or []))
                if pid and toks:
                    pid_map[(cid, toks)] = pid
                    active += 1
            logger.info("fetch_aura_pid_map: chain=%d → %d active / %d total", cid, active, len(pools))
        except Exception as exc:
            logger.warning("fetch_aura_pid_map falló chain=%d: %s", cid, exc)
    return pid_map


def pools_to_dataframe(pools: list[dict[str, Any]], chain_id: int = 8453, pid_map: dict | None = None) -> pd.DataFrame:  # === MULTI-CHAIN SUPPORT ===
    rows: list[dict[str, Any]] = []
    for p in pools:
        ut = frozenset(t.lower() for t in (p.get("underlyingTokens") or []))
        aura_pid: str | None = None
        best_score = 0
        if pid_map and ut:
            for (cid, toks), pid in pid_map.items():
                # Match: all Aura tokens appear in DeFiLlama's token set.
                # Boosted pools have more tokens on DeFiLlama than on Aura,
                # so we check aura_toks ⊆ ut (not the other way around).
                # Pick the largest matching Aura token set to avoid false positives.
                if cid == chain_id and toks and toks.issubset(ut):
                    score = len(toks)
                    if score > best_score:
                        best_score = score
                        aura_pid = pid
        url = (
            f"https://app.aura.finance/#/{chain_id}/pool/{aura_pid}"
            if aura_pid else
            f"https://app.aura.finance/#/{chain_id}"
        )
        rows.append({
            "Symbol":        p.get("symbol"),
            "TVL_USD":       p.get("tvlUsd"),
            "APY_Total":     p.get("apy"),
            "APY_Base":      p.get("apyBase"),
            "APY_Reward":    p.get("apyReward"),
            "Pool_ID":       p.get("pool"),
            "Type":          classify_pool(p),
            "URL":           url,
            "Stablecoin_Flag": bool(p.get("stablecoin", False)),
            "Protocol":      "Aura",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("APY_Total", ascending=False, na_position="last").reset_index(drop=True)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_aura_base_pools(chain: str = "Base") -> pd.DataFrame:
    """Pipeline completo: descarga → filtra Aura/<chain> → tabula."""
    chain_id = CHAINS.get(chain, {}).get("id", 8453)  # === MULTI-CHAIN SUPPORT ===
    all_pools = fetch_all_pools()
    chain_lower = chain.lower()
    aura = [
        p for p in all_pools
        if isinstance(p.get("project"), str)
        and "aura" in p["project"].lower()
        and isinstance(p.get("chain"), str)
        and p["chain"].lower() == chain_lower
    ]
    logger.info("Filtrado a %d pools de Aura en %s", len(aura), chain)
    pid_map = fetch_aura_pid_map()
    return pools_to_dataframe(aura, chain_id=chain_id, pid_map=pid_map)  # === MULTI-CHAIN SUPPORT ===


@st.cache_data(ttl=300, show_spinner=False)
def fetch_aave_pools(chain: str = "Base") -> pd.DataFrame:
    """Pipeline: descarga → filtra Aave/<chain> → tabula con URLs de Aave.

    Args:
        chain: Nombre de la chain (e.g. "Base", "Ethereum").

    Returns:
        DataFrame con columnas compatibles con pools_to_dataframe + Protocol="Aave".
    """
    all_pools = fetch_all_pools()
    chain_lower = chain.lower()
    aave = [
        p for p in all_pools
        if isinstance(p.get("project"), str)
        and p["project"].lower().startswith("aave")
        and isinstance(p.get("chain"), str)
        and p["chain"].lower() == chain_lower
    ]
    logger.info("Filtrado a %d pools de Aave en %s", len(aave), chain)
    rows: list[dict[str, Any]] = []
    for p in aave:
        rows.append({
            "Symbol":          p.get("symbol"),
            "TVL_USD":         p.get("tvlUsd"),
            "APY_Total":       p.get("apy"),
            "APY_Base":        p.get("apyBase"),
            "APY_Reward":      p.get("apyReward"),
            "Pool_ID":         p.get("pool"),
            "Type":            classify_pool(p),
            "URL":             build_aave_url(p, chain),
            "Stablecoin_Flag": bool(p.get("stablecoin", False)),
            "Protocol":        "Aave",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("APY_Total", ascending=False, na_position="last").reset_index(drop=True)
    return df


# =========================================================================== #
# Helpers: formato y colores
# =========================================================================== #

def fmt_usd(v: float | None, decimals: int = 0) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"${v:,.{decimals}f}"


def fmt_pct(v: float | None, decimals: int = 2) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.{decimals}f}%"


def apy_emoji(apy: float | None) -> str:
    if apy is None or pd.isna(apy):
        return "⚪"
    if apy >= 8:
        return "🟢"
    if apy >= 4:
        return "🟡"
    return "🔴"


def compounding_fv(principal: float, annual_apy_pct: float, months: int) -> float:
    """Valor futuro con compounding mensual: FV = P·(1 + r/12)^n."""
    if principal <= 0 or months <= 0:
        return float(principal)
    monthly_rate = (annual_apy_pct / 100.0) / 12.0
    return principal * (1.0 + monthly_rate) ** months


def compounding_table(principal: float, annual_apy_pct: float, months: int) -> pd.DataFrame:
    """DataFrame mes-a-mes con balance, ganancia mensual y acumulada."""
    monthly_rate = (annual_apy_pct / 100.0) / 12.0
    rows, balance = [], principal
    for m in range(1, months + 1):
        prev    = balance
        balance = balance * (1.0 + monthly_rate)
        rows.append({
            "Mes": m,
            "Balance": balance,
            "Ganancia mensual": balance - prev,
            "Ganancia acumulada": balance - principal,
        })
    return pd.DataFrame(rows)


def plotly_dark_layout(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "paper_bgcolor": "#0e1117",
        "plot_bgcolor":  "#14161f",
        "font":     {"color": "#fafafa", "family": "sans-serif"},
        "xaxis":    {"gridcolor": "#2a2f3d", "linecolor": "#2a2f3d", "zerolinecolor": "#2a2f3d"},
        "yaxis":    {"gridcolor": "#2a2f3d", "linecolor": "#2a2f3d", "zerolinecolor": "#2a2f3d"},
        "hoverlabel": {"bgcolor": "#1a1d29", "bordercolor": "#00ff9d", "font": {"color": "#fafafa"}},
        "margin":   {"l": 50, "r": 30, "t": 50, "b": 40},
        "legend":   {"bgcolor": "rgba(20,22,31,0.6)", "bordercolor": "#2a2f3d", "borderwidth": 1},
    }
    base.update(overrides)
    return base


# =========================================================================== #
# Sidebar
# =========================================================================== #

with st.sidebar:
    # === MULTI-CHAIN SUPPORT === Chain name in sidebar subtitle
    _chain_name = st.session_state.get("selected_chain", "Base")
    st.markdown(
        "<div style='padding:0.6rem 0 0.2rem 0;'>"
        "<span style='font-size:1.6rem;'>📈</span>"
        "<span style='font-size:1.15rem; font-weight:700; color:#00ff9d; margin-left:6px;'>"
        "AuraYieldTracker</span>"
        f"<div style='color:#8b93a7; font-size:0.8rem; margin-top:2px;'>Stables · {_chain_name} Chain</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Refresh button prominente ──
    if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.toast("Cache limpiada — recargando datos...", icon="🔄")
        st.rerun()

    # === FIX 1: Auto-refresh real con countdown ===
    auto_refresh = st.checkbox("⏱️ Auto-refresh", value=False,
                               help="Recarga automática en el intervalo elegido.")
    if auto_refresh:
        interval = st.select_slider("Intervalo (min)", options=[5, 15, 30, 60],
                                    value=st.session_state.refresh_interval)
        st.session_state.refresh_interval = interval
        interval_secs = interval * 60

        if st.session_state.refresh_start is None:
            st.session_state.refresh_start = time.time()

        elapsed = time.time() - st.session_state.refresh_start
        remaining = max(0.0, interval_secs - elapsed)

        if remaining == 0:
            st.session_state.refresh_start = time.time()
            st.cache_data.clear()
            st.rerun()

        mins, secs = divmod(int(remaining), 60)
        countdown_ph = st.empty()
        countdown_ph.caption(f"⏱️ Próximo refresh en **{mins}:{secs:02d}** min")
        time.sleep(1)
        st.rerun()
    else:
        st.session_state.refresh_start = None

    st.divider()

    # === MULTI-CHAIN SUPPORT === Active chain selector
    st.selectbox(
        "🔗 Chain",
        options=list(CHAINS.keys()),
        key="selected_chain",
        on_change=_reset_pool_on_chain_change,
        help="Selecciona la red a monitorear.",
    )

    st.radio(
        "📡 Protocolo",
        options=["Aura Finance", "Aave v3", "Ambos"],
        key="selected_protocol",
        on_change=_reset_pool_on_chain_change,
        help="Filtra los pools por protocolo DeFi.",
    )

    st.number_input(
        "💰 Depósito (USD)",
        min_value=0.0, max_value=10_000_000.0,
        value=float(st.session_state.deposit_usd),
        step=100.0, format="%.2f",
        key="deposit_usd",
        help="Valor compartido entre Overview y el Simulador.",
    )

    st.divider()
    st.markdown("**Filtros**")
    st.checkbox(
        "Solo Stables",
        value=st.session_state.only_stables,
        key="only_stables",
        help="Filtra a pools clasificados como Stable o Semi-stable.",
    )

    st.divider()
    _proto_sb = st.session_state.get("selected_protocol", "Aura Finance")
    _chain_id_sb = CHAINS[_chain_name]["id"]
    if _proto_sb == "Aura Finance":
        _protocol_links = f"🟣 [Aura Finance · {_chain_name}](https://app.aura.finance/#/{_chain_id_sb})  \n"
    elif _proto_sb == "Aave v3":
        _protocol_links = f"👻 [Aave v3 · {_chain_name}](https://app.aave.com/markets/)  \n"
    else:
        _protocol_links = (
            f"🟣 [Aura Finance · {_chain_name}](https://app.aura.finance/#/{_chain_id_sb})  \n"
            "👻 [Aave v3](https://app.aave.com/markets/)  \n"
        )
    st.markdown(
        _protocol_links
        + "📊 [DeFiLlama Yields](https://defillama.com/yields)  \n"
        "🐦 [Twitter · Aura](https://twitter.com/AuraFinance)"
    )
    st.divider()
    st.caption(
        f"Dashboard de monitoreo para pools de stablecoins en {_proto_sb} "
        f"(chain {_chain_name}). Datos vía DeFiLlama API · Cache 5 min.\n\n"
        "⚠️ *No es asesoramiento financiero.* APYs variables, riesgos de "
        "smart-contract, de-peg e impermanent loss."
    )


# =========================================================================== #
# Data loading
# =========================================================================== #

# fetch cached; chain + protocol params differentiate cache keys
_active_protocol = st.session_state.get("selected_protocol", "Aura Finance")
with st.spinner("📡 Cargando pools desde DeFiLlama..."):
    try:
        _chain_sel = st.session_state.selected_chain
        if _active_protocol == "Aura Finance":
            df_all = fetch_aura_base_pools(chain=_chain_sel)
        elif _active_protocol == "Aave v3":
            df_all = fetch_aave_pools(chain=_chain_sel)
        else:  # Ambos
            _df_aura = fetch_aura_base_pools(chain=_chain_sel)
            _df_aave = fetch_aave_pools(chain=_chain_sel)
            df_all = pd.concat([_df_aura, _df_aave], ignore_index=True).sort_values(
                "APY_Total", ascending=False, na_position="last"
            ).reset_index(drop=True)
        load_error: str | None = None
    except Exception as exc:  # noqa: BLE001
        df_all = pd.DataFrame()
        load_error = str(exc)

if load_error:
    st.error(
        f"❌ **Error al cargar datos de DeFiLlama.**\n\n"
        f"```\n{load_error}\n```\n\n"
        "Posibles causas: API temporalmente caída, rate-limit o falla de red. "
        "Esperá 1-2 minutos y pulsá **🔄 Refresh Data** en el sidebar."
    )
    st.stop()

if df_all.empty:
    st.warning(
        f"⚠️ No se encontraron pools de {_active_protocol} en {st.session_state.selected_chain} en este momento. "
        "Pulsá **🔄 Refresh Data** en el sidebar para reintentar."
    )
    st.stop()

# ── Filtro según sidebar ──
df_view = df_all.copy()
if st.session_state.only_stables:
    df_view = df_view[df_view["Type"].isin(["Stable", "Semi-stable"])].reset_index(drop=True)

if df_view.empty:  # === MULTI-CHAIN SUPPORT ===
    st.warning(
        f"⚠️ No hay pools de stables activos en Aura {st.session_state.selected_chain} ahora mismo. "
        "Desactivá **Solo Stables** en el sidebar para ver el universo completo."
    )
    st.stop()

# ── Listas de pools compartidas (calculadas antes del sidebar y los tabs) ──
_pool_by_apy = df_view.sort_values("APY_Total", ascending=False, na_position="last")
_sb_ids    = _pool_by_apy["Pool_ID"].tolist()
_sb_labels = [
    f"{r['Symbol']}  ·  {fmt_pct(r['APY_Total'])}"
    for _, r in _pool_by_apy.iterrows()
]
_pool_by_tvl = df_view.sort_values("TVL_USD", ascending=False, na_position="last")
_ov_ids    = _pool_by_tvl["Pool_ID"].tolist()
_ov_labels = [
    f"{r['Symbol']}  ·  TVL {fmt_usd(r['TVL_USD'])}  ·  APY {fmt_pct(r['APY_Total'])}"
    for _, r in _pool_by_tvl.iterrows()
]

# Default: mayor TVL en primera carga o cambio de chain
if st.session_state.selected_pool_id not in _ov_ids:
    st.session_state.selected_pool_id = _ov_ids[0] if _ov_ids else None


def _sb_pool_change() -> None:
    label = st.session_state.get("pool_selector")
    if label not in _sb_labels:
        return
    new_id = _sb_ids[_sb_labels.index(label)]
    st.session_state.selected_pool_id = new_id
    if new_id in _ov_ids:
        st.session_state["pool_selector_ov"] = _ov_labels[_ov_ids.index(new_id)]


def _ov_pool_change() -> None:
    label = st.session_state.get("pool_selector_ov")
    if label not in _ov_labels:
        return
    new_id = _ov_ids[_ov_labels.index(label)]
    st.session_state.selected_pool_id = new_id
    if new_id in _sb_ids:
        st.session_state["pool_selector"] = _sb_labels[_sb_ids.index(new_id)]


# ── Pool selector (sidebar) ──
with st.sidebar:
    st.divider()
    st.markdown("**🎯 Pool activo**")
    _sb_default = (
        _sb_ids.index(st.session_state.selected_pool_id)
        if st.session_state.selected_pool_id in _sb_ids else 0
    )
    st.selectbox(
        "Pool (ordenados por APY ↓)",
        options=_sb_labels, index=_sb_default,
        key="pool_selector",
        on_change=_sb_pool_change,
    )

# =========================================================================== #
# Welcome banner + header principal
# =========================================================================== #

now_utc  = datetime.now(pytz.UTC)
ts_art   = now_utc.astimezone(pytz.timezone("America/Argentina/Buenos_Aires"))
ts_label = ts_art.strftime("%Y-%m-%d %H:%M ART")

# === MULTI-CHAIN SUPPORT === Dynamic chain name in welcome banner
_active_chain = st.session_state.selected_chain
st.markdown(
    "<div class='welcome-banner'>"
    f"<h2>📈 AuraYieldTracker · Stables {_active_chain}</h2>"
    f"<p>Monitoreo en tiempo real de pools de stablecoins de Aura Finance en {_active_chain} – "
    "APY, TVL y simulador de compounding. "
    "Herramienta pública y gratuita · Datos de "
    "<a href='https://defillama.com/yields' target='_blank'>DeFiLlama</a>.</p>"
    "</div>",
    unsafe_allow_html=True,
)

col_h1, col_h2, col_h3 = st.columns([2, 1, 1])
with col_h1:
    st.markdown(
        f"**{len(df_view)}** pools de stables encontrados · "
        f"Última actualización: `{ts_label}`"
    )
with col_h2:
    best = df_view.iloc[0] if not df_view.empty else None
    if best is not None:
        st.metric("🏆 Mejor APY", fmt_pct(best["APY_Total"]),
                  delta=best["Symbol"], delta_color="off")
with col_h3:
    total_tvl = df_view["TVL_USD"].sum()
    st.metric("💧 TVL total (stables)", fmt_usd(total_tvl))


# =========================================================================== #
# Tabs (orden: Overview | Todos los Pools | Simulador | Histórico)
# =========================================================================== #

tab_ov, tab_table, tab_sim, tab_hist = st.tabs([  # === MULTI-CHAIN SUPPORT ===
    f"🎯 Overview · {_active_chain}",
    f"📋 Pools de Stables · {_active_chain}",
    "🧮 Simulador de Compounding",
    "📊 Histórico & Análisis",
])


# --------------------------------------------------------------------------- #
# Tab 1 · Overview del pool seleccionado
# --------------------------------------------------------------------------- #
with tab_ov:
    # ── Pool selector dentro del tab (ordenado por TVL ↓) ──
    _ov_default = _ov_ids.index(st.session_state.selected_pool_id) if st.session_state.selected_pool_id in _ov_ids else 0
    st.selectbox(
        "🎯 Pool",
        options=_ov_labels,
        index=_ov_default,
        key="pool_selector_ov",
        on_change=_ov_pool_change,
    )
    selected = df_view[df_view["Pool_ID"] == st.session_state.selected_pool_id].iloc[0]
    st.session_state["sim_current_pool_apy"] = (
        float(selected["APY_Total"]) if pd.notna(selected["APY_Total"]) else 0.0
    )

    deposit  = float(st.session_state.deposit_usd)
    sym      = selected["Symbol"]
    tvl      = selected["TVL_USD"]
    apy      = selected["APY_Total"]
    apy_base = selected["APY_Base"]
    apy_rew  = selected["APY_Reward"]
    pool_id  = selected["Pool_ID"]
    ptype    = selected["Type"]

    # === FIX 3: Pool header prominente con badge y link directo ===
    _badge_colors = {"Stable": "#00ff9d", "Semi-stable": "#ffd700", "Volatile": "#ff4b4b"}
    _badge_col = _badge_colors.get(ptype, "#888888")
    _chain_id  = CHAINS.get(st.session_state.get("selected_chain", "Base"), {}).get("id", 8453)
    _pool_url  = selected.get("URL") or f"https://app.aura.finance/#/{_chain_id}"
    st.markdown(
        f"""
        <div style="background:#1a1a2e;border-left:5px solid {_badge_col};
                    padding:18px 22px;border-radius:10px;margin-bottom:18px;
                    display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
          <div>
            <span style="font-size:1.7rem;font-weight:800;color:#ffffff;letter-spacing:.5px">
              {apy_emoji(apy)} {sym}
            </span>
            <span style="background:{_badge_col};color:#000;padding:3px 12px;border-radius:14px;
                         font-size:.78rem;font-weight:700;margin-left:10px;vertical-align:middle">
              {ptype}
            </span>
            <div style="color:#8888aa;font-size:.8rem;margin-top:4px">
              Pool ID: <code style="color:#aaaacc">{pool_id}</code>
            </div>
          </div>
          <a href="{_pool_url}" target="_blank"
             style="background:{_badge_col};color:#000;font-weight:700;padding:8px 16px;
                    border-radius:8px;text-decoration:none;font-size:.88rem;white-space:nowrap">
            🔗 Ver en Aura Finance ↗
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    apy_pct        = float(apy) if pd.notna(apy) else 0.0
    annual_simple  = deposit * (apy_pct / 100.0)
    monthly_simple = annual_simple / 12.0
    fv_12m         = compounding_fv(deposit, apy_pct, 12)
    fv_gain_12m    = fv_12m - deposit

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Symbol",          sym)
    m2.metric("TVL actual",      fmt_usd(tvl))
    m3.metric("APY Total",       fmt_pct(apy),
              delta=f"{apy_emoji(apy)} {'alto' if apy_pct >= 8 else 'medio' if apy_pct >= 4 else 'bajo'}",
              delta_color="off")
    m4.metric("Retorno mensual", fmt_usd(monthly_simple, 2),
              delta="(simple)", delta_color="off")

    m5, m6, m7, m8 = st.columns(4)
    m5.metric("Retorno anual (simple)",        fmt_usd(annual_simple, 2))
    m6.metric("Proyección 12m (compounding)", fmt_usd(fv_12m, 2),
              delta=f"+{fmt_usd(fv_gain_12m, 2)}")
    m7.metric("APY Base",   fmt_pct(apy_base))
    m8.metric("APY Reward", fmt_pct(apy_rew))

    st.caption(f"📌 Depósito base: {fmt_usd(deposit, 2)} · Datos: {ts_label}")
    st.divider()

    # ── Chart histórico ──
    st.markdown("#### 📈 Histórico APR del pool")
    with st.spinner("Descargando histórico..."):
        hist_ov = fetch_pool_chart(pool_id)

    if hist_ov.empty or "timestamp" not in hist_ov.columns:
        st.info("Sin datos históricos disponibles para este pool en DeFiLlama.")
    else:
        window_days = st.radio(
            "Ventana temporal", [30, 60, 90, 180], index=0,
            horizontal=True, key="hist_window_overview",
        )
        cutoff = hist_ov["timestamp"].max() - pd.Timedelta(days=window_days)
        hwin   = hist_ov[hist_ov["timestamp"] >= cutoff].copy()

        fig = go.Figure()
        if "apy" in hwin.columns:
            fig.add_trace(go.Scatter(
                x=hwin["timestamp"], y=hwin["apy"], name="APY Total",
                line=dict(color="#00ff9d", width=2.5),
                hovertemplate="%{x|%Y-%m-%d}<br>APY: %{y:.2f}%<extra></extra>",
            ))
        if "apyBase" in hwin.columns:
            fig.add_trace(go.Scatter(
                x=hwin["timestamp"], y=hwin["apyBase"], name="APY Base",
                line=dict(color="#8a8ffc", width=1.6, dash="dot"),
            ))
        if "apyReward" in hwin.columns:
            fig.add_trace(go.Scatter(
                x=hwin["timestamp"], y=hwin["apyReward"], name="APY Reward",
                line=dict(color="#ffd700", width=1.6, dash="dot"),
            ))
        fig.update_layout(**plotly_dark_layout(
            title=f"{sym} — APR histórico · últimos {window_days} días",
            yaxis_title="APY (%)", xaxis_title="", height=420,
        ))
        st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# Tab 2 · Tabla completa de stables
# --------------------------------------------------------------------------- #
with tab_table:
    st.markdown(f"### 📋 Todos los pools de stables — Aura · {_active_chain}")  # === MULTI-CHAIN SUPPORT ===

    col_f1, col_f2, col_f3, col_f4 = st.columns([1.2, 1.2, 1.4, 1.2])
    with col_f1:
        max_apy_av = float(df_view["APY_Total"].max() or 20.0)
        min_apy    = st.slider("APY mínimo (%)", 0.0, max(max_apy_av, 20.0), 0.0, step=0.5)
    with col_f2:
        min_tvl = st.number_input("TVL mínimo (USD)", min_value=0.0, value=0.0,
                                  step=10_000.0, format="%.0f")
    with col_f3:
        search = st.text_input("🔍 Buscar symbol", placeholder="USDC, GHO, crvUSD…")
    with col_f4:
        st.checkbox(
            "Solo stables puros",
            value=st.session_state.pure_stables_only,
            key="pure_stables_only",
            help="Pools marcados stablecoin=True por DeFiLlama.",
        )

    df_table = df_view.copy()
    if st.session_state.pure_stables_only:
        df_table = df_table[df_table["Type"] == "Stable"]
    df_table = df_table[
        (df_table["APY_Total"].fillna(0) >= min_apy) &
        (df_table["TVL_USD"].fillna(0)   >= min_tvl)
    ]
    if search:
        df_table = df_table[df_table["Symbol"].str.contains(search, case=False, na=False)]

    # === FIX 4a: Columna retorno mensual estimado con depósito actual ===
    _deposit_now = float(st.session_state.deposit_usd)
    df_table = df_table.copy()
    df_table["Retorno mensual est."] = df_table["APY_Total"].fillna(0).apply(
        lambda apy: _deposit_now * ((1 + apy / 100) ** (1 / 12) - 1)
    )

    if df_table.empty:
        st.info("No hay pools que cumplan los filtros actuales.")
    else:
        # === FIX 2: Click-to-select — on_select actualiza selected_pool_id ===
        _show_protocol_col = st.session_state.get("selected_protocol", "Aura Finance") == "Ambos"
        _table_cols = (
            ["Symbol", "Protocol", "Type", "TVL_USD", "APY_Total", "APY_Base",
             "APY_Reward", "Retorno mensual est.", "Pool_ID", "URL"]
            if _show_protocol_col else
            ["Symbol", "Type", "TVL_USD", "APY_Total", "APY_Base",
             "APY_Reward", "Retorno mensual est.", "Pool_ID", "URL"]
        )
        _col_config: dict = {
            "Symbol":               st.column_config.TextColumn("Symbol",                width="medium"),
            "Protocol":             st.column_config.TextColumn("Protocolo",             width="small"),
            "Type":                 st.column_config.TextColumn("Tipo",                  width="small"),
            "TVL_USD":              st.column_config.NumberColumn("TVL",                 format="$%,.0f"),
            "APY_Total":            st.column_config.NumberColumn("APY Total",           format="%.2f%%"),
            "APY_Base":             st.column_config.NumberColumn("APY Base",            format="%.2f%%"),
            "APY_Reward":           st.column_config.NumberColumn("APY Reward",          format="%.2f%%"),
            "Retorno mensual est.": st.column_config.NumberColumn("Retorno mensual est.",format="$%.2f"),
            "Pool_ID":              st.column_config.TextColumn("Pool ID",               width="medium"),
            "URL":                  st.column_config.LinkColumn("Link",                  display_text="↗"),
        }
        sel = st.dataframe(
            df_table[_table_cols],
            use_container_width=True,
            height=560,
            column_config=_col_config,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="pool_table_selection",
        )
        if sel.selection.rows:
            _clicked_idx = sel.selection.rows[0]
            _clicked_id  = df_table.iloc[_clicked_idx]["Pool_ID"]
            if _clicked_id != st.session_state.selected_pool_id:
                st.session_state.selected_pool_id = _clicked_id
                st.toast(
                    f"Pool seleccionado: {df_table.iloc[_clicked_idx]['Symbol']}",
                    icon="✅",
                )
                st.rerun()
        st.caption(
            f"Mostrando **{len(df_table)}** de **{len(df_view)}** pools filtrados. "
            f"Haz clic en una fila para seleccionar el pool en Overview."
        )


# --------------------------------------------------------------------------- #
# Tab 3 · Simulador de compounding
# --------------------------------------------------------------------------- #
with tab_sim:
    # === FIX DINAMISMO SIMULADOR ===
    st.markdown("### 🧮 Simulador de compounding mensual")
    st.caption(
        "Fórmula: **FV = P · (1 + r/12)ⁿ**. No contempla gas, slippage "
        "ni variaciones del APY — es una proyección teórica de referencia."
    )

    # ── Opciones dinámicas: pools de la chain activa ordenados por APY ──
    _sim_df = df_view[df_view["APY_Total"].notna()].sort_values("APY_Total", ascending=False)
    _sim_pool_labels = [
        f"{r['Symbol']}  ·  {fmt_pct(r['APY_Total'])}"
        for _, r in _sim_df.iterrows()
    ]
    _sim_apy_map: dict[str, float] = {
        f"{r['Symbol']}  ·  {fmt_pct(r['APY_Total'])}": float(r['APY_Total'])
        for _, r in _sim_df.iterrows()
    }
    _sim_options = _sim_pool_labels + ["Custom"]

    # Si el preset guardado ya no existe (cambio de chain), usar el pool con mayor APY
    if st.session_state.get("sim_preset") not in _sim_options:
        st.session_state["sim_preset"] = _sim_pool_labels[0] if _sim_pool_labels else "Custom"

    def _sim_pool_select() -> None:
        preset = st.session_state["sim_preset"]
        if preset in _sim_apy_map:
            st.session_state["sim_apy"] = min(_sim_apy_map[preset], 50.0)

    col_s1, col_s2, col_s3 = st.columns([1.2, 1.2, 1.2])
    with col_s1:
        st.number_input(
            "Monto inicial (USD)",
            min_value=0.0, max_value=10_000_000.0,
            value=float(st.session_state.deposit_usd),
            step=100.0, format="%.2f",
            key="sim_deposito",
        )
    with col_s2:
        _sim_default_idx = (
            _sim_options.index(st.session_state["sim_preset"])
            if st.session_state["sim_preset"] in _sim_options else 0
        )
        st.selectbox(
            f"Pool ({_active_chain})",
            options=_sim_options,
            index=_sim_default_idx,
            key="sim_preset",
            on_change=_sim_pool_select,
        )
    with col_s3:
        st.slider("Meses a proyectar", min_value=1, max_value=60, key="sim_meses")

    # Sincronización inline: si no es Custom, forzar APY antes de dibujar el slider
    _preset_now = st.session_state.get("sim_preset", "Custom")
    if _preset_now != "Custom" and _preset_now in _sim_apy_map:
        st.session_state["sim_apy"] = min(_sim_apy_map[_preset_now], 50.0)

    st.slider(
        "APY asumido (%)", min_value=0.0, max_value=50.0, step=0.1,
        key="sim_apy",
        on_change=_sim_apy_to_custom,
    )

    principal = st.session_state["sim_deposito"]
    apy_used  = st.session_state["sim_apy"]
    months    = st.session_state["sim_meses"]

    tbl = compounding_table(principal, apy_used, months)
    if tbl.empty:
        st.info("Ingresá un monto y meses > 0 para simular.")
    else:
        fv        = float(tbl.iloc[-1]["Balance"])
        gain      = fv - principal
        no_comp   = principal * (1 + apy_used / 100.0 * months / 12.0)
        extra_vs  = fv - no_comp
        eff_apy   = ((fv / principal) ** (12 / months) - 1) * 100 if principal and months else 0.0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Balance final",            fmt_usd(fv, 2))
        k2.metric("Ganancia total",           fmt_usd(gain, 2),
                  delta=f"+{fmt_pct(gain / principal * 100 if principal else 0)}")
        k3.metric("Extra vs. interés simple", fmt_usd(extra_vs, 2),
                  delta="efecto compounding", delta_color="off")
        k4.metric("APY efectivo",             fmt_pct(eff_apy))

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=tbl["Mes"], y=tbl["Ganancia mensual"], name="Ganancia mensual",
            marker_color="#00ff9d", opacity=0.65,
            hovertemplate="Mes %{x}<br>+%{y:$,.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=tbl["Mes"], y=tbl["Balance"], name="Balance acumulado",
            line=dict(color="#ffd700", width=3), yaxis="y2",
            hovertemplate="Mes %{x}<br>Balance %{y:$,.2f}<extra></extra>",
        ))
        fig.update_layout(**plotly_dark_layout(
            title=f"Crecimiento con APY {apy_used:.2f}% durante {months} meses",
            xaxis_title="Mes",
            yaxis=dict(title="Ganancia mensual (USD)", gridcolor="#2a2f3d"),
            yaxis2=dict(title="Balance (USD)", overlaying="y", side="right",
                        gridcolor="#2a2f3d", tickformat="$,.0f"),
            height=440, barmode="group",
        ))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### 📅 Detalle mes a mes")
        st.dataframe(
            tbl, use_container_width=True, hide_index=True,
            column_config={
                "Mes":                st.column_config.NumberColumn("Mes",                 format="%d"),
                "Balance":            st.column_config.NumberColumn("Balance",             format="$%,.2f"),
                "Ganancia mensual":   st.column_config.NumberColumn("Ganancia mensual",    format="$%,.2f"),
                "Ganancia acumulada": st.column_config.NumberColumn("Ganancia acumulada",  format="$%,.2f"),
            },
        )


# --------------------------------------------------------------------------- #
# Tab 4 · Histórico & análisis completo
# --------------------------------------------------------------------------- #
with tab_hist:
    st.markdown(f"### 📊 Histórico & análisis — {selected['Symbol']}")

    with st.spinner("Cargando histórico completo..."):
        hist_full = fetch_pool_chart(selected["Pool_ID"])

    if hist_full.empty:
        st.info(
            "No hay datos históricos disponibles para este pool en DeFiLlama. "
            "Intentá seleccionar otro pool o volvé más tarde."
        )
    else:
        apy_s   = hist_full["apy"].dropna() if "apy" in hist_full.columns else pd.Series(dtype=float)
        last_30 = hist_full[hist_full["timestamp"] >= hist_full["timestamp"].max() - pd.Timedelta(days=30)]["apy"].dropna()
        last_7  = hist_full[hist_full["timestamp"] >= hist_full["timestamp"].max() - pd.Timedelta(days=7)]["apy"].dropna()

        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("APY prom. 7d",     fmt_pct(last_7.mean()  if not last_7.empty  else None))
        s2.metric("APY prom. 30d",    fmt_pct(last_30.mean() if not last_30.empty else None))
        s3.metric("Máximo histórico", fmt_pct(apy_s.max()    if not apy_s.empty   else None))
        s4.metric("Mínimo histórico", fmt_pct(apy_s.min()    if not apy_s.empty   else None))
        s5.metric("Volatilidad (σ)",  fmt_pct(apy_s.std()    if not apy_s.empty   else None))

        fig2 = go.Figure()
        if "apy" in hist_full.columns:
            fig2.add_trace(go.Scatter(
                x=hist_full["timestamp"], y=hist_full["apy"], name="APY (%)",
                line=dict(color="#00ff9d", width=2),
                hovertemplate="%{x|%Y-%m-%d}<br>APY %{y:.2f}%<extra></extra>",
            ))
        if "tvlUsd" in hist_full.columns:
            fig2.add_trace(go.Scatter(
                x=hist_full["timestamp"], y=hist_full["tvlUsd"], name="TVL (USD)",
                line=dict(color="#ffd700", width=2, dash="dot"), yaxis="y2",
                hovertemplate="%{x|%Y-%m-%d}<br>TVL %{y:$,.0f}<extra></extra>",
            ))
        fig2.update_layout(**plotly_dark_layout(
            title="APY vs. TVL — historia completa",
            xaxis_title="",
            yaxis=dict(title="APY (%)", gridcolor="#2a2f3d"),
            yaxis2=dict(title="TVL (USD)", overlaying="y", side="right",
                        gridcolor="#2a2f3d", tickformat="$,.0f"),
            height=460,
        ))
        st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### 📤 Exportar datos")
        e1, e2, e3 = st.columns(3)
        with e1:
            st.download_button(
                "⬇️ Pools filtrados (CSV)",
                data=df_view.to_csv(index=False).encode("utf-8"),
                file_name=f"aura_stables_{_active_chain.lower()}_{now_utc.strftime('%Y%m%d_%H%M')}.csv",  # === MULTI-CHAIN SUPPORT ===
                mime="text/csv", use_container_width=True,
            )
        with e2:
            st.download_button(
                "⬇️ Histórico del pool (CSV)",
                data=hist_full.to_csv(index=False).encode("utf-8"),
                file_name=f"{selected['Symbol']}_history_{now_utc.strftime('%Y%m%d')}.csv",
                mime="text/csv", use_container_width=True,
            )
        with e3:
            st.download_button(
                "⬇️ Pools (JSON)",
                data=df_view.to_json(orient="records", indent=2).encode("utf-8"),
                file_name=f"aura_stables_{_active_chain.lower()}_{now_utc.strftime('%Y%m%d_%H%M')}.json",  # === MULTI-CHAIN SUPPORT ===
                mime="application/json", use_container_width=True,
            )


# =========================================================================== #
# Footer
# =========================================================================== #

st.markdown(
    f"<div class='app-footer'>"
    f"Datos de <a href='https://defillama.com/yields' target='_blank'>DeFiLlama</a> · "
    f"Última actualización: <strong>{ts_label}</strong> · "
    f"<a href='https://app.aura.finance/#/{CHAINS[_active_chain]['id']}' target='_blank'>Aura Finance · {_active_chain} ↗</a> · "  # === MULTI-CHAIN SUPPORT ===
    f"Cache TTL 5 min · {len(STABLE_TOKENS)} stable-tokens reconocidos"
    f"</div>",
    unsafe_allow_html=True,
)
