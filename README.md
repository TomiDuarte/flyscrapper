# Flyscrapper — Tracker de precios de vuelos (gratis, en GitHub Actions)

Rastrea precios de vuelos **round-trip** (ida y vuelta por la misma ciudad
europea) para varias rutas y fechas de regreso, guarda el histórico en SQLite y
te **avisa por WhatsApp** cuando aparece un precio mínimo o una oferta marcada
como "low" por Google.

Corre **100% gratis en GitHub Actions** (no necesitás tu PC prendida): un cron
lo dispara dos veces por día, hace una barrida y se apaga.

- **Fuente principal:** [`fast-flights`](https://pypi.org/project/fast-flights/) (sin API key).
- **Fallback opcional:** SerpApi (`engine=google_flights`), solo si cargás `SERPAPI_KEY`.
- **Alertas:** WhatsApp vía [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/) (o Telegram, cambiando una variable).

---

## Qué rastrea (por defecto)

| Parámetro        | Valor                                   |
|------------------|-----------------------------------------|
| Orígenes         | `ASU`, `EZE`, `IGU`                     |
| Destinos         | `FRA`, `MAD`                            |
| Rutas            | 6 (producto orígenes × destinos)        |
| Salida           | `2026-12-18` (fija)                     |
| Regresos         | `2027-03-01`, `2027-03-10`              |
| Moneda / pax     | `USD`, 1 adulto, económica              |

Todo esto se ajusta en [`config.py`](config.py) (o por variables de entorno).
Nada está hardcodeado en el resto del código.

---

## Estructura

```
.
├── config.py                 # toda la configuración (rutas, fechas, reintentos, paths)
├── main.py                   # orquesta la barrida (--dry-run / --reset)
├── sources/                  # fuentes de datos, misma interfaz
│   ├── base.py               #   FlightResult + contrato FlightSource
│   ├── fast_flights_source.py#   fuente principal (fast-flights)
│   ├── serpapi_source.py     #   fallback opcional (SerpApi)
│   ├── cache_source.py       #   cache para --dry-run
│   └── utils.py              #   normalización de precio + link a Google Flights
├── storage/db.py             # SQLite: tabla precios + dedupe de alertas
├── alerts/notifier.py        # enviar_alerta(): CallMeBot (WhatsApp) / Telegram
├── data/                     # precios.db (versionado) + cache de dry-run
├── requirements.txt
├── .env.example
└── .github/workflows/tracker.yml
```

---

## Cómo funciona la lógica de alerta

Por cada combinación **ruta + fecha_regreso**:

1. Se busca el precio (con reintentos + backoff; si falla, intenta SerpApi).
2. Se normaliza a número y se guarda en SQLite, recalculando el mínimo histórico.
3. **Se alerta si**:
   - es el **primer registro** de esa combinación, **o**
   - el precio es **menor** al `precio_historico_mas_bajo`, **o**
   - Google marca el precio como **`low`** (`ALERTAR_SI_LOW=1`).
4. **Dedupe**: la misma oferta (misma ruta+regreso+precio+motivo) no se repite.

El mensaje de WhatsApp incluye ruta, fechas, precio, moneda, mínimo anterior,
% de baja y un **link directo a Google Flights** para reservar rápido.

---

## Uso local (desarrollo)

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # completá tus datos

# Barrida sin tocar la red (usa data/cache_dryrun.json):
python main.py --dry-run

# Reiniciar el piso histórico:
python main.py --reset --dry-run

# Barrida real contra la red:
#   en tu PC sin navegador headless, usá FETCH_MODE=fallback (en el .env)
python main.py
```

> Para `FETCH_MODE=local` (el más robusto) hace falta instalar el navegador:
> `python -m playwright install chromium`. En tu PC podés evitarlo usando
> `FETCH_MODE=fallback`.

---

## Puesta en marcha en GitHub Actions (paso a paso)

### 1. Crear el repo y subir el código
```bash
git init
git add .
git commit -m "Flyscrapper: tracker de precios de vuelos"
git branch -M main
git remote add origin https://github.com/<TU_USUARIO>/<TU_REPO>.git
git push -u origin main
```
> Podés crear el repo **privado**; Actions funciona igual y tenés ~2000
> minutos/mes gratis, de sobra para 2 corridas diarias.

### 2. Activar CallMeBot (WhatsApp)
1. Agendá el número de CallMeBot: **+34 644 51 95 23**.
2. Enviale por WhatsApp el mensaje: **`I allow callmebot to send me messages`**.
3. El bot te responde con tu **APIKEY**.
4. Guardá tu teléfono (con `+` y código de país, ej. `+595981123456`) y esa APIKEY.

### 3. Cargar los Secrets del repo
En **Settings → Secrets and variables → Actions → New repository secret**, creá:

| Secret              | Obligatorio | Valor                                   |
|---------------------|-------------|-----------------------------------------|
| `CALLMEBOT_PHONE`   | Sí          | Tu teléfono, ej. `+595981123456`        |
| `CALLMEBOT_APIKEY`  | Sí          | La APIKEY que te dio CallMeBot          |
| `SERPAPI_KEY`       | No          | Solo si querés el fallback de SerpApi   |

### 4. Permisos de Actions
- **Settings → Actions → General → Workflow permissions** → elegí
  **Read and write permissions** (permite que el job commitee la base).
  > El workflow ya declara `permissions: contents: write`, pero esta opción del
  > repo debe estar habilitada.

### 5. Verificar el cron
- Probá primero a mano: **Actions → Flight Price Tracker → Run workflow**
  (`workflow_dispatch`).
- Revisá el log del paso *Ejecutar tracker* y confirmá que llega el WhatsApp.
- El `schedule` corre a las **11:00 y 23:00 UTC**. Ajustá los `cron:` en
  [`.github/workflows/tracker.yml`](.github/workflows/tracker.yml) si querés otro
  horario (GitHub usa siempre UTC).

> **Nota sobre el cron de GitHub:** los schedules pueden demorarse algunos
> minutos en disparar y, en repos sin actividad por mucho tiempo, GitHub puede
> pausarlos; con commits regulares (este job los hace) se mantienen activos.

---

## Detalles de implementación

- **`fetch_mode`**: se usa `local` en CI (Playwright propio, sin depender de
  endpoints serverless de terceros). El workflow instala Chromium con
  `playwright install --with-deps chromium`.
- **Moneda**: `fast-flights` no fija la moneda; en los runners de GitHub
  (US) los precios suelen venir en USD. Si necesitás USD garantizado, activá el
  fallback de **SerpApi**, que sí acepta `currency=USD`.
- **Robustez**: cada ruta va en su propio `try/except`; si una falla, se loguea
  y la barrida sigue. Reintentos con backoff exponencial + `sleep` entre rutas.
- **El push de la base**: el job hace `commit` con `[skip ci]` y luego
  `git pull --rebase --autostash` + `push` con el `GITHUB_TOKEN` integrado, para
  no generar conflictos ni loops de CI.

---

## Cambiar a Telegram

1. Creá un bot con [@BotFather](https://t.me/BotFather) y obtené el `TELEGRAM_TOKEN`.
2. Conseguí tu `TELEGRAM_CHAT_ID`.
3. Cargá ambos como Secrets y agregá `ALERT_BACKEND=telegram` (env/Secret).

No hace falta tocar código: `alerts/notifier.py` ya trae el canal de Telegram.
