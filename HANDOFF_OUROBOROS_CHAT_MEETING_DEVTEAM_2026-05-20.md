# Handoff Ouroboros Chat Meeting + Development Team

Datum: 2026-05-20

## Repos en branches

- WintripAI: `/home/pwintri2/WintripAI`
- Branch: `codex/guided-behavioral-apprenticeship`
- Laatste relevante commit: `362f88b Add chaired meeting types and dev team planner`
- Chat app: `/home/pwintri2/ouroboros-chat`
- Branch: `backup/ouroboros-chat-20260519-143915`
- Laatste relevante commit: `a44cfe6 Add meeting modes and development team workspace`

## Wat is gebouwd

- De meeting runner is voorzitter-geleid:
  - De voorzitter start standaard.
  - De voorzitter geeft deelnemers het woord.
  - De voorzitter vat samen, sluit af en kan ingrijpen.
- Anti-papegaai-logica:
  - Als twee niet-voorzitter persona's inhoudelijk te veel herhalen, wordt een `intervention` turn toegevoegd.
  - De voorzitter vraagt dan om een nieuw onderscheidend punt, ander risico of bewijsstuk.
- Drie vergadertypes:
  - `team`: standaard teamvergadering.
  - `sprint_planning`: snel plan met taken, risico, test en stopregel.
  - `brainstorm`: voorzitter-geleide researchsessie met extra Brave Search-context per persona wanneer web search aan staat.
- Meeting persistence bewaart nu ook `meeting_type`.
- Frontend:
  - Segmentkeuze voor Team vergadering, Sprint planning en Brainstormsessie.
  - Transcriptlabels voor nieuwe fases zoals `grijpt in`, `plant`, `onderzoekt`, `synthese`.
  - Voorzitter blijft visueel herkenbaar; lampje blijft knipperen bij actieve spreker.
- Ontwikkelteam:
  - Apart scherm naast Meeting.
  - Selectie van persona's en CLI-agents.
  - Provider/model-keuze voor OpenAI, Gemini/Google en lokale Ollama-modellen.
  - Genereert een approval-gated slash-agent prompt.
  - Voert bewust geen shell, browser, patch of CLI uit binnen de standalone chat-router.

## Veiligheidsgrens

Het ontwikkelteam is plan-only in de standalone chat app. Werkelijke agentische uitvoering hoort via de bestaande Cockpit slash-agent routes, met de bestaande approval-flow en approval phrase:

`Akkoord`

Dit is bewust zo gehouden vanwege de project guardrails: geen stille externe acties, geen shell/patch/browser/CLI zonder expliciete toestemming.

## Verificatie

Uitgevoerd en groen:

```bash
python3 -m unittest sandbox_tests.test_ouroboros_chat_service sandbox_tests.test_ouroboros_chat_routes sandbox_tests.test_ouroboros_chat_personas_meetings
```

Resultaat:

- 25 tests uitgevoerd
- 9 skipped
- OK

Frontend:

```bash
cd /home/pwintri2/ouroboros-chat
npm run build
npx tauri build --bundles deb
```

Resultaat:

- TypeScript/Vite build OK
- Tauri release build OK
- Deb bundle:
  `/home/pwintri2/ouroboros-chat/src-tauri/target/release/bundle/deb/Ouroboros Chat_0.1.0_amd64.deb`

## Runtime status

- Backend container was online op `127.0.0.1:8010`.
- Standalone Tauri release binary draaide als:
  `/home/pwintri2/ouroboros-chat/src-tauri/target/release/ouroboros-chat`

## Belangrijke bestanden

Backend:

- `controller/ouroboros_chat.py`
- `sandbox_tests/test_ouroboros_chat_service.py`
- `sandbox_tests/test_ouroboros_chat_routes.py`

Frontend:

- `/home/pwintri2/ouroboros-chat/src/App.tsx`
- `/home/pwintri2/ouroboros-chat/src/styles.css`

## Let op bij vervolgwerk

- De WintripAI worktree bevat veel bestaande, niet-gerelateerde wijzigingen en untracked bestanden. Niet zomaar alles stagen.
- Niet wijzigen zonder expliciete instructie:
  - `.secrets/`
  - `wintrip_brain/`
  - `data/chromadb/`
  - caches en gegenereerde model/vector-store payloads
- Brave Search-context komt via de Cockpit key-status en bestaande `controller.brave_search` route.
- API keys, OAuth tokens en bearer material nooit in context, memory of handoff opslaan.

## Mogelijke volgende stappen

- Ontwikkelteam optioneel koppelen aan een expliciete Cockpit-uitvoerknop die pas actief wordt na `Akkoord`.
- Brainstormresultaten visueel bronrijker tonen, bijvoorbeeld per bronlaag of bron-URL.
- Meeting transcript live streamen per turn in plaats van pas na afronding.
- Saved meetings filterbaar maken op vergadertype.
