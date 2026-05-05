# Handoff Fase 8 Standalone - 2026-05-05

## Status

Branch: `feature/esoteric-ouroboros-architecture`

Laatste afgeronde werkstroom:
- Brave Search is server-side ingebouwd naast bestaande browser research.
- Browser research geeft nu browserobservatie plus Brave LLM Context in een payload.
- Knowledge acquisition ondersteunt `brave` en `gemma_brave` als leerpaden.
- Ouroboros model-runtime exposeert een compacte 11D pocket met vaste dimensies.
- Cockpit chat, slash agents en Living Ouroboros zijn gescheiden in de UI/backend envelope.
- `/agents` toont weer alleen slash catalogus en lekt geen `living_echo`, thought of whisper in de chatregel.
- Codex Agent kan goedgekeurd werk als Codex runtime job indienen en redigeert secret-achtige tekst voor persistentie.

## Belangrijkste bestanden

- `controller/brave_search.py`: Brave Search client, status, web search, LLM Context en 50 rps limiter.
- `controller/browser_research.py`: directe browser research kan Brave companion context toevoegen.
- `controller/agent_tools.py`: nieuwe `brave_search` tool en Brave companion bij `browser_research`.
- `controller/main.py`: Brave endpoints, browser+Brave route, model runtime status en gescheiden slash/living chat envelope.
- `controller/knowledge_acquisition.py`: Brave LLM Context opslag in 11D training records.
- `controller/ouroboros_model.py` en `Modelfile.ouroboros`: model-runtime contract via 11D pocket.
- `ouroboros_cockpit/src/App.tsx`: Brave provider key UI, betere object rendering, slash catalogus zonder thought/whisper menging.
- `controller/codex_agent.py`: approval-gated Codex runtime intent en redactie van secret-achtige tekst.

## Runtime checks

Gedraaid en groen:

```bash
docker exec -w /workspace wintrip-standalone-ui python3 -m unittest sandbox_tests.test_browser_research sandbox_tests.test_agent_tools sandbox_tests.test_tauri_backend_routes sandbox_tests.test_slash_agent_router sandbox_tests.test_brave_search -v
docker exec -w /workspace wintrip-standalone-ui python3 -m unittest sandbox_tests.test_api_key_store sandbox_tests.test_knowledge_acquisition sandbox_tests.test_learning_accelerator sandbox_tests.test_ouroboros_model -v
npm run build
```

Live rooktests na restart:

```bash
curl -sS http://localhost:8010/api/ouroboros/search/brave/status
curl -sS -X POST http://localhost:8010/api/ouroboros/research/browser -H 'content-type: application/json' --data '{"query":"Ouroboros 11D pockets","approval":"Akkoord","limit":2}'
curl -sS -X POST http://localhost:8010/api/cockpit/chat -H 'content-type: application/json' --data '{"provider":"google","model":"gemini-test","prompt":"/agents"}'
```

Waargenomen:
- Brave status: `configured`, `rate_limit_per_second=50`.
- Browser research: `browser_observed`, `brave_status=success`, `brave_matches=2`.
- `/agents`: `route=slash_agent`, `agent=catalog`, `has_living_echo=false`.
- Normale chat houdt Living echo wel beschikbaar.

## Niet meenemen als codewijziging

Deze runtime/artifact wijzigingen stonden in de werkboom en zijn bewust buiten de commit gehouden:
- `wintrip_brain/**`
- `*.docx`, `*.odt`
- `.~lock.*`

Ze zijn runtime/data-state of lokale documenten, geen source patch voor deze handoff.

## Volgende focus

1. Laat de Cockpit een aparte visuele baan houden voor Chat, Agent Jobs en Living events.
2. Laat `gemma_brave` kleine batches draaien en controleer Chroma growth per batch.
3. Voeg, als Philip dat wil, een knop toe die expliciet `brave_search` draait zonder browseractie.
4. Commit runtime-data alleen als daar een apart besluit voor komt.
