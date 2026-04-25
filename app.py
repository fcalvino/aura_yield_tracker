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
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2

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

def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("deposit_usd", 3240.00)
    ss.setdefault("selected_pool_id", None)
    ss.setdefault("only_stables", True)
    ss.setdefault("pure_stables_only", False)
    # === FIX 1: Auto-refresh state ===
    ss.setdefault("refresh_start", None)
    ss.setdefault("refresh_interval", 15)


_init_state()


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


def pools_to_dataframe(pools: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for p in pools:
        rows.append({
            "Symbol":        p.get("symbol"),
            "TVL_USD":       p.get("tvlUsd"),
            "APY_Total":     p.get("apy"),
            "APY_Base":      p.get("apyBase"),
            "APY_Reward":    p.get("apyReward"),
            "Pool_ID":       p.get("pool"),
            "Type":          classify_pool(p),
            "URL": p.get("url") or (
                f"https://app.aura.finance/#/8453/pool/{p.get('pool')}"
                if p.get("pool") else ""
            ),
            "Stablecoin_Flag": bool(p.get("stablecoin", False)),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("APY_Total", ascending=False, na_position="last").reset_index(drop=True)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def fetch_aura_base_pools(chain: str = "Base") -> pd.DataFrame:
    """Pipeline completo: descarga → filtra Aura/Base → tabula."""
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
    return pools_to_dataframe(aura)


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
    st.markdown(
        "<div style='padding:0.6rem 0 0.2rem 0;'>"
        "<span style='font-size:1.6rem;'>📈</span>"
        "<span style='font-size:1.15rem; font-weight:700; color:#00ff9d; margin-left:6px;'>"
        "AuraYieldTracker</span>"
        "<div style='color:#8b93a7; font-size:0.8rem; margin-top:2px;'>Stables · Base Chain</div>"
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

    st.selectbox(
        "🔗 Chain",
        options=["Base ✅", "Ethereum (próximo)", "Arbitrum (próximo)"],
        index=0, disabled=True,
        help="Por ahora solo Base. Ethereum y Arbitrum en roadmap.",
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
    st.markdown(
        "🔗 [Aura Finance · Base](https://app.aura.finance/#/8453)  \n"
        "📊 [DeFiLlama Yields](https://defillama.com/yields)  \n"
        "🐦 [Twitter · Aura](https://twitter.com/AuraFinance)"
    )
    st.divider()
    st.caption(
        "Dashboard público de monitoreo para pools de stablecoins en Aura Finance "
        "(chain Base). Datos vía DeFiLlama API · Cache 5 min.\n\n"
        "⚠️ *No es asesoramiento financiero.* APYs variables, riesgos de "
        "smart-contract, de-peg e impermanent loss."
    )


# =========================================================================== #
# Data loading
# =========================================================================== #

@st.cache_data(ttl=300, show_spinner=False)
def _load_pools() -> pd.DataFrame:
    return fetch_aura_base_pools(chain="Base")


with st.spinner("📡 Cargando pools desde DeFiLlama..."):
    try:
        df_all = _load_pools()
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
        "⚠️ No se encontraron pools de Aura en Base en este momento. "
        "Pulsá **🔄 Refresh Data** en el sidebar para reintentar."
    )
    st.stop()

# ── Filtro según sidebar ──
df_view = df_all.copy()
if st.session_state.only_stables:
    df_view = df_view[df_view["Type"].isin(["Stable", "Semi-stable"])].reset_index(drop=True)

if df_view.empty:
    st.warning(
        "⚠️ No hay pools de stables activos en Aura Base ahora mismo. "
        "Desactivá **Solo Stables** en el sidebar para ver el universo completo."
    )
    st.stop()

# ── Pool selector (sidebar, después del filtro) ──
with st.sidebar:
    st.divider()
    st.markdown("**🎯 Pool activo**")
    pool_sorted = df_view.sort_values("APY_Total", ascending=False, na_position="last")
    labels = [
        f"{r['Symbol']}  ·  {fmt_pct(r['APY_Total'])}"
        for _, r in pool_sorted.iterrows()
    ]
    ids = pool_sorted["Pool_ID"].tolist()

    if st.session_state.selected_pool_id not in ids:
        st.session_state.selected_pool_id = ids[0] if ids else None

    default_idx = (
        ids.index(st.session_state.selected_pool_id)
        if st.session_state.selected_pool_id in ids
        else 0
    )
    selected_label = st.selectbox(
        "Pool (ordenados por APY ↓)",
        options=labels, index=default_idx,
        key="pool_selector",
    )
    st.session_state.selected_pool_id = ids[labels.index(selected_label)]

selected = df_view[df_view["Pool_ID"] == st.session_state.selected_pool_id].iloc[0]


# =========================================================================== #
# Welcome banner + header principal
# =========================================================================== #

now_utc  = datetime.now(pytz.UTC)
ts_art   = now_utc.astimezone(pytz.timezone("America/Argentina/Buenos_Aires"))
ts_label = ts_art.strftime("%Y-%m-%d %H:%M ART")

st.markdown(
    "<div class='welcome-banner'>"
    "<h2>📈 AuraYieldTracker · Stables Base</h2>"
    "<p>Monitoreo en tiempo real de pools de stablecoins de Aura Finance en Base – "
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

tab_ov, tab_table, tab_sim, tab_hist = st.tabs([
    "🎯 Overview",
    "📋 Todos los Pools de Stables",
    "🧮 Simulador de Compounding",
    "📊 Histórico & Análisis",
])


# --------------------------------------------------------------------------- #
# Tab 1 · Overview del pool seleccionado
# --------------------------------------------------------------------------- #
with tab_ov:
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
    _pool_url  = selected.get("URL") or "https://app.aura.finance/#/base/pool"
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
    st.markdown("### 📋 Todos los pools de stables — Aura · Base")

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
        sel = st.dataframe(
            df_table[["Symbol", "Type", "TVL_USD", "APY_Total", "APY_Base",
                      "APY_Reward", "Retorno mensual est.", "Pool_ID", "URL"]],
            use_container_width=True,
            height=560,
            column_config={
                "Symbol":               st.column_config.TextColumn("Symbol",                width="medium"),
                "Type":                 st.column_config.TextColumn("Tipo",                  width="small"),
                "TVL_USD":              st.column_config.NumberColumn("TVL",                 format="$%,.0f"),
                "APY_Total":            st.column_config.NumberColumn("APY Total",           format="%.2f%%"),
                "APY_Base":             st.column_config.NumberColumn("APY Base",            format="%.2f%%"),
                "APY_Reward":           st.column_config.NumberColumn("APY Reward",          format="%.2f%%"),
                "Retorno mensual est.": st.column_config.NumberColumn("Retorno mensual est.",format="$%.2f"),
                "Pool_ID":              st.column_config.TextColumn("Pool ID",               width="medium"),
                "URL":                  st.column_config.LinkColumn("Link",                  display_text="↗"),
            },
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
    st.markdown("### 🧮 Simulador de compounding mensual")
    st.caption(
        "Fórmula: **FV = P · (1 + r/12)ⁿ**. No contempla gas, slippage "
        "ni variaciones del APY — es una proyección teórica de referencia."
    )

    col_s1, col_s2, col_s3 = st.columns([1.2, 1.2, 1.2])
    with col_s1:
        principal = st.number_input(
            "Monto inicial (USD)",
            min_value=0.0, max_value=10_000_000.0,
            value=float(st.session_state.deposit_usd),
            step=100.0, format="%.2f",
        )
    with col_s2:
        preset_apy = st.radio(
            "Preset APY",
            ["Conservador 4%", "Base 6.5%", "Optimista 12%", "Pool actual", "Custom"],
            index=3, horizontal=False,
        )
    with col_s3:
        months = st.slider("Meses a proyectar", min_value=1, max_value=60, value=12)

    current_pool_apy = float(selected["APY_Total"]) if pd.notna(selected["APY_Total"]) else 0.0
    preset_map = {
        "Conservador 4%": 4.0,
        "Base 6.5%": 6.5,
        "Optimista 12%": 12.0,
        "Pool actual": current_pool_apy,
    }
    default_apy = preset_map.get(preset_apy, current_pool_apy)
    apy_used = st.slider(
        "APY asumido (%)", min_value=0.0, max_value=50.0,
        value=float(default_apy), step=0.1,
    )

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
                file_name=f"aura_stables_base_{now_utc.strftime('%Y%m%d_%H%M')}.csv",
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
                file_name=f"aura_stables_base_{now_utc.strftime('%Y%m%d_%H%M')}.json",
                mime="application/json", use_container_width=True,
            )


# =========================================================================== #
# Footer
# =========================================================================== #

st.markdown(
    f"<div class='app-footer'>"
    f"Datos de <a href='https://defillama.com/yields' target='_blank'>DeFiLlama</a> · "
    f"Última actualización: <strong>{ts_label}</strong> · "
    f"<a href='https://app.aura.finance/#/8453' target='_blank'>Aura Finance ↗</a> · "
    f"Cache TTL 5 min · {len(STABLE_TOKENS)} stable-tokens reconocidos"
    f"</div>",
    unsafe_allow_html=True,
)
