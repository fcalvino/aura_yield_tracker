# 📈 AuraYieldTracker · Stables Base

> **Monitoreo en tiempo real de pools de stablecoins de Aura Finance en Base – APY, TVL y simulador de compounding.**

Dashboard público construido con **Streamlit**, datos de **DeFiLlama** y cero dependencias privadas.
Accesible por cualquier persona (o IA) vía URL pública en Streamlit Community Cloud.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

---

## 🚀 Deploy en Streamlit Community Cloud — Tutorial paso a paso

### Paso 1 · Crear repositorio en GitHub

1. Andá a [github.com/new](https://github.com/new).
2. Nombre del repo: `aura-yield-tracker` (o el que prefieras).
3. Visibilidad: **Public** (necesario para el plan gratuito de Streamlit Cloud).
4. **No** inicialices con README (ya tenés uno).
5. Hacé click en **Create repository**.

---

### Paso 2 · Subir todos los archivos al repo

**Opción A — Git por consola (recomendado):**

```bash
# Desde la carpeta del proyecto
cd aura_yield_tracker

# Inicializar git si no lo hiciste antes
git init
git remote add origin https://github.com/TU_USUARIO/aura-yield-tracker.git

# Crear .gitignore ANTES de hacer commit
cat > .gitignore << 'EOF'
.venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
output/
.streamlit/secrets.toml
EOF

# Agregar todos los archivos (secrets.toml queda excluido por .gitignore)
git add .
git commit -m "feat: AuraYieldTracker v2.0 - production ready"
git branch -M main
git push -u origin main
```

**Opción B — GitHub web (drag & drop):**

1. Abrí tu repo recién creado en GitHub.
2. Hacé click en **"uploading an existing file"**.
3. Arrastrá estos archivos/carpetas:
   - `app.py`
   - `requirements.txt`
   - `.streamlit/config.toml`
   - `utils/__init__.py`
   - `utils/data_fetcher.py` *(si lo usás como módulo separado)*
4. Escribí el commit message: `feat: initial deploy` y hacé click en **Commit changes**.

> ⚠️ **Nunca subas `.streamlit/secrets.toml`** — contiene configuración privada. Ya está en el `.gitignore`.

**Estructura mínima requerida en el repo:**

```
tu-repo/
├── app.py                      ← entry point (obligatorio)
├── requirements.txt            ← dependencias (obligatorio)
├── .streamlit/
│   └── config.toml             ← tema oscuro premium
└── README.md
```

---

### Paso 3 · Ir a Streamlit Community Cloud

1. Abrí [share.streamlit.io](https://share.streamlit.io).
2. Si no tenés cuenta, hacé click en **"Sign up"** → autenticá con tu cuenta de GitHub.
3. Una vez logueado, verás tu dashboard de apps.

---

### Paso 4 · Conectar el repo y desplegar

1. En el dashboard de Streamlit Cloud, hacé click en **"New app"** (botón azul arriba a la derecha).

2. Completá el formulario:

   | Campo | Valor |
   |-------|-------|
   | **Repository** | `TU_USUARIO/aura-yield-tracker` |
   | **Branch** | `main` |
   | **Main file path** | `app.py` |
   | **App URL** | Podés customizarlo, ej: `aura-yield-tracker` |

3. (Opcional) Si en el futuro usás secrets, hacé click en **"Advanced settings"** → pegá el contenido de tu `secrets.toml` en el campo **Secrets**.

4. Hacé click en **"Deploy!"**.

5. Streamlit Cloud va a:
   - Clonar tu repo
   - Instalar las dependencias de `requirements.txt`
   - Levantar la app en `https://TU_USUARIO-aura-yield-tracker-app-XXXX.streamlit.app`

6. El primer deploy tarda **2-4 minutos**. Verás los logs en tiempo real en la pantalla.

---

### Paso 5 · Cómo actualizar después del primer deploy

Cada vez que hagas un `git push` a `main`, Streamlit Cloud detecta el cambio y **redespliega automáticamente** en ~1-2 minutos.

```bash
# Flujo de actualización estándar
git add app.py                         # o los archivos que modificaste
git commit -m "fix: mejora en simulador"
git push origin main
# → Streamlit Cloud detecta el push y redespliega solo
```

Para forzar un redeploy sin cambios de código:

1. Abrí tu app en Streamlit Cloud.
2. Hacé click en el ícono **⋮ (tres puntos)** arriba a la derecha.
3. Seleccioná **"Reboot app"**.

---

### Paso 6 · Compartir el link público

Una vez desplegada, tu app tiene una URL pública permanente del tipo:

```
https://TU_USUARIO-aura-yield-tracker-app-XXXX.streamlit.app
```

Podés compartir este link con cualquier persona. La app es completamente pública, sin login ni autenticación.

**Tips para un link más corto:**
- En el formulario de deploy, el campo **"App URL"** te permite elegir el slug.
- Ejemplo: `https://aura-yield-tracker.streamlit.app`

---

## 🗂️ Estructura del proyecto

```
aura_yield_tracker/
├── app.py                    ← Dashboard Streamlit (entry point)
├── requirements.txt          ← Dependencias Python
├── README.md                 ← Este archivo
├── .gitignore                ← Excluye .venv, __pycache__, secrets.toml
│
├── .streamlit/
│   ├── config.toml           ← Tema oscuro premium + configuración Cloud
│   └── secrets.toml          ← PLANTILLA VACÍA — NO subir a GitHub
│
└── utils/                    ← (opcional, si usás módulo separado)
    ├── __init__.py
    └── data_fetcher.py
```

> **Nota:** `app.py` es autocontenido — incluye toda la lógica de fetching.
> La carpeta `utils/` es legacy y puede omitirse al hacer deploy.

---

## 🛠️ Stack técnico

| Componente | Versión | Uso |
|------------|---------|-----|
| Streamlit | ≥ 1.32 | Framework UI / servidor web |
| Pandas | ≥ 2.1 | Transformaciones de datos |
| Plotly | ≥ 5.18 | Gráficos interactivos |
| Requests | ≥ 2.31 | Llamadas HTTP a DeFiLlama |
| pytz | ≥ 2024.1 | Timestamps ART/UTC |

---

## ⚙️ Funcionalidad

### Tabs del dashboard

| Tab | Contenido |
|-----|-----------|
| 🎯 **Overview** | Métricas del pool seleccionado: TVL, APY, retorno mensual/anual, proyección 12m con compounding + chart histórico (30/60/90/180d) |
| 📋 **Todos los Pools de Stables** | Tabla interactiva con filtros: APY mínimo, TVL mínimo, búsqueda por symbol, solo stables puros |
| 🧮 **Simulador de Compounding** | FV = P·(1+r/12)^n, presets 4%/6.5%/12%/pool actual, chart balance vs ganancia, tabla mes a mes |
| 📊 **Histórico & Análisis** | Chart APY vs TVL full history, stats (promedios 7d/30d, máx, mín, σ), exports CSV/JSON |

### Sidebar

- **🔄 Refresh Data** — limpia cache y re-fetcha la API (botón prominente)
- **⏱️ Auto-refresh** — recarga automática cada 5/15/30/60 min
- **💰 Depósito** — compartido entre Overview y Simulador (default: $3,240)
- **Solo Stables** — filtra a pools Stable + Semi-stable
- **Pool activo** — selector ordenado por APY descendente

### Clasificación automática de pools

| Tipo | Criterio |
|------|----------|
| **Stable** | `stablecoin=True` en DeFiLlama, o todos los tokens del symbol están en `STABLE_TOKENS` |
| **Semi-stable** | Al menos un token es stable |
| **Volatile** | Ningún token reconocido como stable |

`STABLE_TOKENS` incluye ~45 tokens: USDC, USDT, DAI, GHO, crvUSD, LUSD, FRAX, sUSDe, USDe, EURC, aTokens de Aave y más.

---

## 🔌 API utilizada

**DeFiLlama Yields** — API pública, sin API key requerida.

| Endpoint | Uso |
|----------|-----|
| `https://yields.llama.fi/pools` | Catálogo completo de pools (cache 5 min) |
| `https://yields.llama.fi/chart/{pool_id}` | Histórico APY/TVL por pool (cache 5 min) |

Todas las llamadas usan `@st.cache_data(ttl=300)` y reintentos con backoff exponencial.

---

## 💻 Desarrollo local

```bash
# 1. Clonar el repo
git clone https://github.com/TU_USUARIO/aura-yield-tracker.git
cd aura-yield-tracker

# 2. Crear virtualenv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Levantar la app
streamlit run app.py
# → Abre http://localhost:8501
```

---

## 🐛 Troubleshooting

**Error "No se pudo cargar datos de DeFiLlama"**
→ La API pública `https://yields.llama.fi/pools` está caída o hay rate-limit.
→ Esperá 1-2 min y pulsá 🔄 Refresh Data.

**Tabla vacía / no hay pools**
→ Desmarcá "Solo Stables" en el sidebar para ver el universo completo.

**Gráficos vacíos en Overview/Histórico**
→ Pool muy nuevo o DeFiLlama no indexó su histórico. Probá con otro pool.

**Deploy fallido en Streamlit Cloud — ModuleNotFoundError**
→ Verificá que `requirements.txt` esté en la raíz del repo, no en una subcarpeta.

**Deploy fallido — versión de Python incompatible**
→ Podés fijar la versión de Python creando un archivo `runtime.txt` con contenido `python-3.11`.

---

## 📊 Color coding APY

- 🟢 `≥ 8%` — APY alto
- 🟡 `4% – 8%` — APY medio
- 🔴 `< 4%` — APY bajo

---

## ⚠️ Disclaimer

No es asesoramiento financiero. Los APYs reportados son variables y dependen
de emisiones BAL/AURA, precio de esos tokens y TVL del pool. Existen riesgos
de smart-contract, de-peg de stablecoins e impermanent loss (bajo en stable-stable, no cero).

---

## 🗺️ Roadmap

- [ ] Multi-chain (Ethereum mainnet, Arbitrum, Optimism)
- [ ] Fallback al subgraph de Aura cuando DeFiLlama está lageado
- [ ] Alertas Telegram (APY cae > X%, TVL drop, reward termina)
- [ ] Histórico persistente local (parquet) para análisis offline
- [ ] Simulador con gas + slippage
- [ ] Comparador side-by-side de N pools

---

*Datos de [DeFiLlama](https://defillama.com/yields) · [Aura Finance](https://app.aura.finance/#/8453)*
