"""Configuration for AuraYieldTracker.

Centraliza todos los parámetros ajustables del proyecto. No incluye secretos:
si en fases posteriores se agregan API keys (Dune, Telegram, etc.) se leerán
vía variables de entorno (os.environ) y NUNCA se hardcodean aquí.
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
# Parámetros de negocio
# --------------------------------------------------------------------------- #

#: Depósito (USD) usado en los cálculos de rendimiento.
DEPOSIT_USD: float = 3240.00

#: Palabras clave que deben aparecer (TODAS) en el campo ``symbol`` del pool
#: objetivo. Se compara case-insensitive. Aura suele usar tokens como
#: "USDC-GHO", "AAVE-USDC-AAVE-GHO", etc. Mantener ambos tokens asegura match
#: aunque el prefijo "aave" cambie.
TARGET_POOL_KEYWORDS: list[str] = ["USDC", "GHO"]

#: Cadena (chain) a filtrar en DeFiLlama. Coincide con el campo ``chain``
#: devuelto por el endpoint /pools (case-insensitive).
TARGET_CHAIN: str = "Base"

#: Substring a matchear contra el campo ``project`` de DeFiLlama (case-insensitive).
TARGET_PROJECT_SUBSTRING: str = "aura"

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

BASE_DIR: Path = Path(__file__).resolve().parent
OUTPUT_DIR: Path = BASE_DIR / "output"
HISTORICAL_DIR: Path = BASE_DIR / "historical"

# --------------------------------------------------------------------------- #
# APIs
# --------------------------------------------------------------------------- #

# NOTA: el enunciado original menciona https://api.llama.fi/yields/pools.
# El endpoint oficial y estable que sirve el JSON de yields es en realidad:
#     https://yields.llama.fi/pools
# Ambos enrutan al mismo backend; usamos el canónico por estabilidad.
DEFILLAMA_POOLS_URL: str = "https://yields.llama.fi/pools"
DEFILLAMA_CHART_URL: str = "https://yields.llama.fi/chart/{pool_id}"  # para Fase 3

# Subgraph de Aura Finance en Base (fallback / on-chain precision).
AURA_SUBGRAPH_BASE_URL: str = (
    "https://api.subgraph.ormilabs.com/api/public/"
    "396b336b-4ed7-469f-a8f4-468e1e26e9a8/"
    "subgraphs/aura-finance-base/v0.0.1/"
)

# --------------------------------------------------------------------------- #
# Red / reintentos
# --------------------------------------------------------------------------- #

REQUEST_TIMEOUT_SECONDS: int = 30
MAX_RETRIES: int = 3
RETRY_BACKOFF_SECONDS: int = 2  # backoff exponencial: RETRY_BACKOFF * attempt

# --------------------------------------------------------------------------- #
# Umbrales / warnings
# --------------------------------------------------------------------------- #

TVL_WARNING_THRESHOLD_USD: float = 100_000.0  # por debajo → warning de liquidez
