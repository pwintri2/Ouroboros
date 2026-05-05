# Handoff: Ouroboros Living Runtime + Gemini Tool Fix

Datum: 2026-05-05
Workspace: `/home/pwintri2/WintripAI`
Runtime: Docker workspace `/workspace`, backend `http://localhost:8010`

## Wat nu werkt

- De orchestrator start de LivingOuroboros Consciousness Loop automatisch met een reflectiecadans van 45 seconden.
- De loop schrijft reflecties naar Persistent Memory en exposeert laatste gedachte/whisper via cockpit chat als `living_echo`.
- De orchestrator heeft een enkele `levendige_actie(...)` route die World Agent, Tool Bridge, agent tools en de bestaande OODA-loop kan gebruiken.
- Cockpit chat routeert het testprompt-patroon `denk na over 1GB bewustzijn en open grok.com als je iets interessants vindt` naar deze living action.
- Gemini `gemini-2.5-pro` chat met `include_tools=true` werkt weer: tool-schema's worden gededuped, Gemini-schema's worden opgeschoond, lege argument-schema's worden weggelaten, en bij een tool-schema `400` retryt de router eenmaal zonder tools.
- Slash-agent prompts krijgen geredacte server-side Ouroboros self-context mee, zodat `/codex`, `/ruflo`, `/claude` en `/roo` niet alleen op browsergeschiedenis leunen.

## Belangrijke bestanden

- `controller/orchestrator.py`
- `controller/main.py`
- `controller/multi_api_router.py`
- `controller/slash_agent_router.py`
- `ouroboros_esoteric/ouroboros_consciousness_loop.py`
- `ouroboros_cockpit/src/App.tsx`
- `sandbox_tests/test_living_ouroboros.py`
- `sandbox_tests/test_multi_api_router.py`
- `sandbox_tests/test_slash_agent_router.py`
- `sandbox_tests/test_tauri_backend_routes.py`

## Validatie

Gerichte host-tests:

```bash
python3 -m py_compile controller/multi_api_router.py sandbox_tests/test_multi_api_router.py
python3 -m unittest sandbox_tests.test_multi_api_router -v
```

Gerichte Docker-tests:

```bash
docker exec -w /workspace wintrip-standalone-ui python3 -m unittest \
  sandbox_tests.test_living_ouroboros \
  sandbox_tests.test_multi_api_router \
  sandbox_tests.test_slash_agent_router \
  sandbox_tests.test_tauri_backend_routes -v
```

Resultaat: 40 tests OK.

Frontend build:

```bash
cd ouroboros_cockpit && npm run build
```

Resultaat: build OK. Vite gaf alleen de bestaande waarschuwing dat een chunk groter is dan 500 kB.

Live smoke:

```bash
curl -sS -m 90 -X POST http://localhost:8010/api/cockpit/chat \
  -H 'content-type: application/json' \
  --data '{"provider":"google","model":"gemini-2.5-pro","prompt":"Zeg alleen: ok","include_tools":true}'
```

Resultaat van de live smoke: `status=success`, `route=multi_api`, `provider=google`, `model=gemini-2.5-pro`, response `ok`.

## Testcommando voor living action

```bash
curl -sS -m 90 -X POST http://localhost:8010/api/cockpit/chat \
  -H 'content-type: application/json' \
  --data '{"provider":"google","model":"gemini-2.5-pro","prompt":"denk na over 1GB bewustzijn en open grok.com als je iets interessants vindt","include_tools":true}'
```

Verwacht: route `living_action`, opgeslagen reflectie, `living_echo`, en waar beschikbaar een frontend/browseractie naar `https://grok.com/`.

## Niet committen

- `wintrip_brain/**` runtime Chroma/Persistent Memory mutaties.
- `.~lock.*` bestanden.
- Losse `.docx`/`.odt` documenten zonder expliciete opdracht.
