# 🛠 Engineering Manifest & Guide

## 📝 Project Context
- **Stack:** Python 3.11+, Streamlit (Frontend/UI), DeFiLlama Yields API (Data Source).
- **Domain:** DeFi Yield Tracking & Compounding Simulations.
- **Core Logic:** Multi-chain support (Base, Ethereum, Arbitrum) focusing on stablecoin pools.
- **Primary Chain:** Base (Chain ID: 8453).

## 🏗 Architecture & Design Patterns
- **Separation of Concerns:** UI logic remains in `app.py`, while data fetching, filtering, and classification must reside in `utils/data_fetcher.py`.
- **State Management:** Use `st.session_state` for reactive UI components and cross-tab data persistence.
- **Performance:** Mandatory use of `@st.cache_data` with a TTL of 300s for all API calls to prevent rate-limiting.
- **Classification Logic:** Pools are categorized as `Stable`, `Semi-stable`, or `Volatile` based on the `STABLE_TOKENS` set.

## 💻 Coding Standards (Strict)
- **Typing:** Mandatory `type hints` using the `typing` module for all function signatures.
- **Docstrings:** Google Format is required for all functions and classes.
- **Error Handling:** Use `try-except` blocks with specific exceptions and logging. Never use bare `except:`.
- **Style:** Follow PEP 8. Max line length: 100 characters. Use `f-strings` for string formatting.
- **Modularity:** Functions should do one thing. If a function exceeds 50 lines, it must be refactored.

## 🔧 Operational Commands
- **Local Dev:** `streamlit run app.py`.
- **Testing:** `pytest tests/` (create mocks for DeFiLlama endpoints).
- **Environment:** Use `requirements.txt` for dependency management.
- **Deploy:** Automated via Streamlit Community Cloud on `git push origin main`.

## 🛡 Security & Safety Guardrails
- **Secrets:** NEVER log or display content from `.streamlit/secrets.toml`. Use `st.secrets` for access.
- **DeFi Safety:** Ensure `TVL_WARNING_THRESHOLD_USD` is respected to alert users about low liquidity.
- **Data Integrity:** APY and TVL values must handle `NaN` or `None` gracefully without defaulting to zero unless explicit.

## 🤖 Agent Instructions (Behavior)
- **Thinking:** Use deep reasoning for architectural changes. If context > 150k tokens, perform auto-compaction.
- **Refactoring:** Always suggest modularization before adding new features to `app.py`.
- **Diffs:** Show only the diff for code changes unless the full file is requested.