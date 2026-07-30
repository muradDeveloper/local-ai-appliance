# Handoff — Weather Tool & Location Context

**Last updated:** 2026-07-29  
**Branch:** `setup/initial-deployment`

---

## Goal

Extend the local AI appliance with a working weather tool for Open WebUI: a FastAPI weather server exposed through Traefik, an Open WebUI Filter that auto-injects the user's location into every conversation, and SearXNG configured to trust the client IP forwarded by Traefik. The LLM should be able to answer weather questions in one tool call without searching for coordinates first.

---

## Project location

- **Working dir:** `/opt/ai-appliance/` (Ubuntu VM) / `C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance` (Windows repo)
- **Read first:** `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`

---

## Working agreement

- Follow all rules in `CLAUDE.md` — particularly: no unsolicited shell commands, health checks must use the container's own runtime (not curl on slim images), all host paths via `.env` variables.
- Never run `docker compose up` commands without being asked.
- Australian English in docs.

---

## Locked decisions

| Decision | Reason |
|---|---|
| Weather server is a custom FastAPI container, not a plugin | Open WebUI tool servers use OpenAPI; a dedicated container gives full control over response shape |
| Open-Meteo `daily` aggregation, 5 days, not `hourly` | Hourly returns 168 rows — floods the LLM context window |
| `reverse_geocoder` removed, replaced with `geoip2` + ip-api.com | `reverse_geocoder` downloads ~100 MB on every build; `geoip2` uses the existing MaxMind DB mounted from the host |
| MaxMind DB mounted read-only from `/etc/elastiflow/maxmind/` | Already present on the VM (shared with ElastiFlow); no separate download needed |
| City geocoding via Open-Meteo geocoding API (not search_web) | Avoids the model making two tool calls (search for coords, then weather); single clean call with `?city=Perth` |
| `operation_id="get_weather_forecast"` pinned in FastAPI decorator | FastAPI auto-generates `get_weather_forecast_forecast_get` which causes the model to guess the wrong name first |
| Location context injected as system message via Open WebUI Filter | Filters can read `__request__` for HTTP headers; no other injection point available |
| LAN IPs fall back to ip-api.com self-lookup for location | MaxMind cannot geolocate RFC-1918 addresses; self-lookup returns the site's public egress IP (same city) |

---

## Done

### Files changed this session

| File | What it does |
|---|---|
| `compose/open-webui/weather/main.py` | FastAPI weather server. Accepts `city` + optional `country` (geocodes via Open-Meteo), or `latitude`/`longitude`, or auto-detects from client IP. Returns current conditions + 5-day daily forecast. Uses MaxMind GeoLite2-City for public IP → city lookup, falls back to ip-api.com for LAN IPs. `operation_id` pinned to `get_weather_forecast`. |
| `compose/open-webui/weather/requirements.txt` | `fastapi`, `uvicorn[standard]`, `pydantic`, `requests`, `geoip2` — trimmed from 8 packages (removed `reverse_geocoder`, `pytz`, `python-dateutil`, `python-multipart`) |
| `compose/open-webui/functions/location_context.py` | Open WebUI Filter (globally active). Reads `X-Forwarded-For`, geolocates via ip-api.com, injects system message with city/lat/lon/timezone. Cached per IP for 1 hour. |
| `compose/searxng/settings.yml` | Added `server.real_ip` block trusting Docker bridge subnets so SearXNG sees the real client IP |
| `compose.yml` | Weather service: added `GEOIP_DB_PATH` volume mount (`${GEOIP_DB_PATH}:/geoip/GeoLite2-City.mmdb:ro`). SearXNG: added `SEARXNG_QUERY_URL` with `region=au-en`, plus `traefik.http.middlewares.searxng-realip.forwardedheaders.trustedips` label. |
| `env_var.cfg` | Added `GEOIP_DB_PATH=/etc/elastiflow/maxmind/GeoLite2-City.mmdb` |

### Infrastructure (already deployed, no changes needed)

- Traefik routing `weather.murs-local.net` → weather container on port 8000
- Open WebUI External Tool connection: `https://weather.murs-local.net` (base URL), spec at `/openapi.json`
- `location_context` Filter installed globally in Open WebUI (toggled via API `POST /api/v1/functions/id/location_context/toggle/global`)

**Overall progress: ~95%** — all code written and tested. Pending: final rebuild deploy on VM.

---

## Next step

The weather server container on the VM still needs rebuilding to pick up the latest `main.py` (city geocoding + MaxMind + pinned operation_id):

```bash
# On the VM in /opt/ai-appliance/
echo "GEOIP_DB_PATH=/etc/elastiflow/maxmind/GeoLite2-City.mmdb" >> .env
docker compose up -d --build --no-deps weather-server
```

After the container is healthy:

1. In Open WebUI Admin → Integrations → Tool Servers → Weather: toggle **off** → Save → toggle **on** → Save (forces re-fetch of updated OpenAPI spec)
2. Test: ask the model "what's the weather in Tokyo?" — should call `get_weather_forecast` once with `city=Tokyo`, no search_web step

---

## What to avoid

- Do **not** use `docker compose up -d --build weather-server` without `--no-deps` — `open-webui` depends on weather-server being healthy and will block indefinitely trying to restart
- Do **not** re-introduce `reverse_geocoder` — it downloads a 100 MB dataset at build time
- Do **not** use `hourly` variables in the Open-Meteo request — returns 168 entries and floods the LLM context
- Do **not** set the Open WebUI tool connection base URL to `https://weather.murs-local.net/openapi.json` — that doubles the path. Base URL must be `https://weather.murs-local.net`
- Do **not** use `is_active` alone for the Filter — it must also be `is_global: true` (set via API toggle, not the UI checkbox)
- Do **not** add cloud LLM providers or expose any internal service port publicly

---

## How to respond

Start with a 1–2 line summary of your understanding of where things stand, then continue from the **Next step** above. Do not restart or re-explain the architecture.
