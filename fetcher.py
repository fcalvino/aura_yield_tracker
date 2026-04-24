"""Data fetching layer for AuraYieldTracker.

Responsable de traer pools desde DeFiLlama (fuente primaria) y, en fases
posteriores, del subgraph de Aura Finance (fallback). Todas las funciones
públicas devuelven estructuras nativas de Python (list/dict) para desacoplar
el fetching de la capa de presentación.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from config import (
    DEFILLAMA_POOLS_URL,
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_SECONDS,
    TARGET_PROJECT_SUBSTRING,
)

logger = logging.getLogger(__name__)


class DataFetchError(RuntimeError):
    """Se lanza cuando falla la obtención de datos tras agotar reintentos."""


# --------------------------------------------------------------------------- #
# DeFiLlama
# --------------------------------------------------------------------------- #

def fetch_defillama_pools() -> list[dict[str, Any]]:
    """Obtiene todos los pools de la API de yields de DeFiLlama.

    Implementa reintentos con backoff exponencial y manejo explícito de
    timeouts, rate-limits (HTTP 429) y errores de red.

    Returns:
        Lista de dicts con los campos nativos de DeFiLlama (``symbol``,
        ``chain``, ``project``, ``tvlUsd``, ``apy``, ``apyBase``,
        ``apyReward``, ``pool``, ``url``, ...).

    Raises:
        DataFetchError: si tras ``MAX_RETRIES`` intentos no se pudo obtener
        una respuesta válida.
    """
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Fetching DeFiLlama pools (attempt %d/%d) — %s",
                attempt, MAX_RETRIES, DEFILLAMA_POOLS_URL,
            )
            resp = requests.get(
                DEFILLAMA_POOLS_URL,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"Accept": "application/json", "User-Agent": "AuraYieldTracker/0.1"},
            )

            if resp.status_code == 429:
                # Rate limit: backoff más agresivo.
                wait = RETRY_BACKOFF_SECONDS * attempt * 3
                logger.warning("Rate-limited (429). Esperando %ds antes de reintentar.", wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            payload = resp.json()

            if not isinstance(payload, dict):
                raise DataFetchError(
                    f"Respuesta inesperada de DeFiLlama (tipo={type(payload).__name__})"
                )

            status = payload.get("status")
            if status and status != "success":
                logger.warning("DeFiLlama devolvió status != success: %r", status)

            pools = payload.get("data", [])
            if not isinstance(pools, list):
                raise DataFetchError("Campo 'data' inesperado en respuesta de DeFiLlama.")

            logger.info("DeFiLlama devolvió %d pools en total.", len(pools))
            return pools

        except requests.Timeout as exc:
            last_error = exc
            logger.warning("Timeout en intento %d: %s", attempt, exc)
        except requests.HTTPError as exc:
            last_error = exc
            logger.warning("HTTPError en intento %d: %s", attempt, exc)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("RequestException en intento %d: %s", attempt, exc)
        except ValueError as exc:
            # json.JSONDecodeError hereda de ValueError.
            last_error = exc
            logger.error("Respuesta no es JSON válido: %s", exc)
            # No tiene sentido reintentar si el backend devuelve basura.
            break

        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_SECONDS * attempt
            logger.info("Reintentando en %ds...", wait)
            time.sleep(wait)

    raise DataFetchError(
        f"No se pudieron obtener pools de DeFiLlama tras {MAX_RETRIES} intentos "
        f"(último error: {last_error!r})"
    )


# --------------------------------------------------------------------------- #
# Filtros y búsqueda
# --------------------------------------------------------------------------- #

def filter_pools(
    pools: list[dict[str, Any]],
    *,
    chain: str,
    project_substring: str = TARGET_PROJECT_SUBSTRING,
) -> list[dict[str, Any]]:
    """Filtra pools por chain y project (ambos case-insensitive).

    Args:
        pools: Lista cruda devuelta por :func:`fetch_defillama_pools`.
        chain: Nombre de la chain a mantener (ej. ``"Base"``).
        project_substring: Substring a buscar en el campo ``project``
            (ej. ``"aura"`` mantiene ``aura-finance``, ``aura``, etc.).

    Returns:
        Nueva lista con los pools que cumplen ambos criterios.
    """
    chain_lower = chain.lower()
    project_lower = project_substring.lower()

    filtered: list[dict[str, Any]] = []
    for pool in pools:
        pool_chain = pool.get("chain")
        pool_project = pool.get("project")
        if not isinstance(pool_chain, str) or not isinstance(pool_project, str):
            continue
        if pool_chain.lower() != chain_lower:
            continue
        if project_lower not in pool_project.lower():
            continue
        filtered.append(pool)

    logger.info(
        "Filtrado a %d pools (chain=%s, project~=%s).",
        len(filtered), chain, project_substring,
    )
    return filtered


def find_target_pool(
    pools: list[dict[str, Any]],
    keywords: list[str],
) -> dict[str, Any] | None:
    """Busca el pool cuyo ``symbol`` contenga TODAS las ``keywords``.

    Si hay varios matches, devuelve el de mayor ``tvlUsd`` (más líquido).

    Args:
        pools: Lista de pools ya filtrados por chain/project.
        keywords: Lista de substrings que deben aparecer en el symbol.

    Returns:
        Dict del pool o ``None`` si no hay match.
    """
    kws = [k.upper() for k in keywords]
    matches: list[dict[str, Any]] = []
    for pool in pools:
        symbol = (pool.get("symbol") or "").upper()
        if all(k in symbol for k in kws):
            matches.append(pool)

    if not matches:
        return None

    # Ordenar por TVL descendente; tvlUsd puede ser None.
    matches.sort(key=lambda p: p.get("tvlUsd") or 0.0, reverse=True)
    if len(matches) > 1:
        logger.info(
            "Se encontraron %d pools con keywords=%s, devolviendo el de mayor TVL.",
            len(matches), keywords,
        )
    return matches[0]
