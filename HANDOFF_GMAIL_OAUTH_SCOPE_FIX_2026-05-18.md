# Handoff: Gmail OAuth Scope Fix + Defensive Client Secret Guard

Datum: 2026-05-18
Branch: `codex/guided-behavioral-apprenticeship`
Commits: [`0e910c6`](https://github.com/pwintri2/Ouroboros/commit/0e910c6), [`bd3c8c7`](https://github.com/pwintri2/Ouroboros/commit/bd3c8c7)
Voorganger: [HANDOFF_CLINE_GRADE_AGENTIC_DELIVERED_2026-05-18.md](HANDOFF_CLINE_GRADE_AGENTIC_DELIVERED_2026-05-18.md)

## Het probleem

Een agentische sessie met doel "vind een formulier om bloed te prikken in Gmail" faalde met `status=error`, `tools_executed=gmail_search` en deze rauwe Google response:

```json
{
  "error": {
    "code": 403,
    "message": "Request had insufficient authentication scopes.",
    "errors": [{"reason": "insufficientPermissions", "domain": "global"}],
    "status": "PERMISSION_DENIED",
    "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT", "metadata": {"service": "gmail.googleapis.com"}}]
  }
}
```

De cockpit had **geen actionable signaal** dat de gebruiker een re-consent moest doen — er kwam alleen een ondoorgrondelijke Google JSON-blob terug. Plus: re-login werd niet aangeboden in de UI.

## Drie lagen oorzaken (in volgorde van diepte)

1. **Default scope te smal.** `DEFAULT_GOOGLE_SCOPES = GOOGLE_SCOPE_PRESETS["gmail_send"]` → alleen `gmail.send`. Bij eerste OAuth setup vroeg de cockpit dus alleen verzend-rechten aan, geen lees-rechten.
2. **Error path gooide rijke details weg.** `_request_json` (google_workspace_adapter.py:467) wrapte HTTPErrors als `{"status":"error","reason":"<string>"}` — de structured `_google_error_details` output (configuration_required, google_reason, etc.) ging verloren.
3. **OAuth consent screen in Google Cloud Console had de extra scopes niet geregistreerd.** Zelfs als de auth URL alle 5 scopes vroeg, strip Google stilzwijgend alles wat de app niet officieel in zijn consent-config heeft staan — geen waarschuwing, geen consent-keuze voor de gebruiker.

Plus een aanverwante bug die tijdens de fix-flow opdook (4):

4. **`_resolve_client_config` kon de saved client_secret overschrijven met lege/korte input.** Mijn eigen `start_google_oauth_flow` calls (met `client_secret=""` om de saved te hergebruiken) hadden hier de saved waarde naar 2 chars gereduceerd, waardoor latere token-exchanges `invalid_client` gaven. Een sluipend gevaar bij elke "save client" UI-actie met lege velden.

## De fix (in twee commits)

### `0e910c6` — Surface Google OAuth scope mismatch with re-login signal

**Backend (`controller/google_oauth_setup.py`)**
- `DEFAULT_GOOGLE_SCOPES = GOOGLE_SCOPE_PRESETS["google_workspace_full"]`. Nieuwe setups vragen direct alle 5 scopes (gmail.readonly + send + modify + drive.metadata.readonly + drive.file).

**Backend (`controller/google_workspace_adapter.py`)**
- `_google_error_details(exc, operation=...)` classificeert nu `ACCESS_TOKEN_SCOPE_INSUFFICIENT` en `insufficient authentication scopes` als `re_login_required: True` en koppelt een `missing_scope` aan via `_OPERATION_SCOPE_HINTS` (search_gmail → gmail.readonly, manage_gmail → gmail.modify, send_gmail → gmail.send, etc.).
- `_request_json` retourneert nu de complete error-dict (status_code, google_reason, message, configuration_required, re_login_required, missing_scope, oauth_start_endpoint, next_action) in plaats van alleen een string.
- `GoogleWorkspaceAdapter.status()` rapporteert `capability_ready` per tool (`{gmail_search:bool, gmail_manage:bool, gmail_send:bool, drive_list:bool}`), `missing_capability_scopes`, `re_login_required` en `oauth_start_endpoint` zodat de UI op één oogopslag ziet welke Gmail/Drive operaties wel/niet werken met het huidige token.

**Backend (`controller/agent_tools.py`)**
- `gmail_search` forward `re_login_required`, `missing_scope` en `oauth_start_endpoint` naar de cockpit payload en gebruikt een actionable `next_action`: *"Google login mist scopes voor Gmail read — open Cockpit > Connectors > Google en klik 'Re-connect Google'. Scope vereist: ..."*

**Frontend (`ouroboros_cockpit/src/components/AgentWorkspace.tsx`)**
- Nieuwe `findGoogleReloginSignal` helper scant de live event-stream op `re_login_required` in payload-summaries.
- Rode banner onder de timeline-summary met "Re-connect Google" knop die naar de Connectors-tab navigeert via een nieuwe `onOpenConnectors` callback prop.

**Frontend (`ouroboros_cockpit/src/App.tsx` + `styles.css`)**
- `onOpenConnectors={() => setActiveTab("connectors")}` doorgegeven aan AgentWorkspace.
- `.agent-relogin-banner` styling (dezelfde tone-warn/block CSS familie).

**Tests (`sandbox_tests/test_google_workspace_scope_errors.py`)** — 4 tests
- `test_scope_insufficient_sets_re_login_required_for_gmail_search`: build een mock HTTP 403 met `ACCESS_TOKEN_SCOPE_INSUFFICIENT`, verifieer `re_login_required=True`, `missing_scope == gmail.readonly`, `oauth_start_endpoint` correct.
- `test_service_disabled_does_not_set_re_login_required`: `SERVICE_DISABLED` met `activationUrl` → `re_login_required=False`, `next_action` bevat "Enable".
- `test_status_reports_missing_capability_scopes`: token met alleen gmail.send → `re_login_required=True`, `capability_ready={gmail_search:False, gmail_send:True, ...}`.
- `test_status_no_re_login_when_all_scopes_present`: token met alle 4 hoofdscopes → geen re-login.

### `bd3c8c7` — Guard Google OAuth client_secret against accidental overwrites

**Backend (`controller/google_oauth_setup.py`)**
- `_resolve_client_config` weigert nu te retourneren met een client_secret korter dan 8 chars als er een saved waarde >= 8 chars bestaat. In plaats daarvan: `status: "blocked"`, `reason: "Refusing to overwrite saved Google client_secret with a value shorter than 8 characters."`.
- Als saved ook leeg is en input < 8 chars: `status: "blocked"`, `reason: "Google OAuth client_secret looks invalid (less than 8 characters)."` zodat de fout vroeg in de chain duidelijk wordt.

**Tests (`sandbox_tests/test_google_oauth_client_secret_guard.py`)** — 5 tests
- `test_empty_input_falls_back_to_saved`: leeg input + saved valid → resolver gebruikt saved.
- `test_short_input_with_long_saved_is_blocked`: 2-char input + saved valid → blocked, niet overschreven.
- `test_short_input_without_saved_is_blocked_with_invalid_reason`: 2-char input + geen saved → blocked met andere reason.
- `test_valid_input_succeeds`: valid input wint van saved (refresh-secret use case).
- `test_missing_both_id_and_secret_is_blocked`: leeg input + leeg saved → blocked met "required" reason.

## Live re-login flow die we doorliepen

Niet code, wel proces. De gebruiker doorliep het volgende:

1. **Code update** (commit `0e910c6`) gepusht en backend restart → `/api/cockpit/connectors/google/oauth/status` toonde 4 missing scopes ten opzichte van de nieuwe default 5.
2. **Authorization URL gegenereerd** via `POST /api/cockpit/connectors/google/oauth/start` met `approval: "Akkoord"` en saved client config. URL bevatte alle 5 scopes met `prompt=consent`.
3. **Eerste re-login mislukt qua scopes**: Google's consent-scherm toonde alleen `gmail.send` omdat het Google Cloud Console OAuth consent screen niet de andere 4 scopes had geregistreerd. Token werd opgeslagen maar nog steeds met 1 scope.
4. **Google Cloud Console handmatige stap** (gebruiker, ~3 min): https://console.cloud.google.com/apis/credentials/consent → "Edit App" → "Add or remove scopes" → voeg gmail.readonly, gmail.modify, drive.metadata.readonly, drive.file toe → Save.
5. **Tweede re-login mislukt qua exchange**: Google toonde nu wel alle 5 scopes, gebruiker approved, callback ontving code — maar exchange faalde met `invalid_client`. Diagnose: `/workspace/.secrets/google_oauth_client.json` had `client_secret length: 2` (corrupt door eerdere lege-input start-calls).
6. **Client secret hersteld via stdin** (niet via argv of logs): gebruiker plakte de `GOCSPX-...` waarde in chat, geschreven naar disk met `chmod 0o600`, exchange direct geslaagd.
7. **Live `gmail_search` succes**: `top status: success`, 1 message gevonden — *"RE: Nieuw bericht via website Contact praktijk Nijdam"* van Praktijk Nijdam.
8. **Defensieve guard** (commit `bd3c8c7`) toegevoegd zodat dit niet opnieuw kan gebeuren.

## Verificatie post-fix

```
focused regression (9 tests: client_secret_guard + workspace_scope_errors)
  → OK in <1s

live, na docker restart wintripai-ouroboros-backend-1:

GET  /api/cockpit/connectors/google/oauth/status
  → status: ready, setup_ready: True, missing_scopes: [], token scopes: 5

POST /agent/tool {tool_name: gmail_status}
  → re_login_required: False, capability_ready: {gmail_search:True, gmail_manage:True, gmail_send:True, drive_list:True}

POST /agent/tool {tool_name: gmail_search, query: "bloed prikken formulier", approval: "Akkoord"}
  → top status: success, count: 1
  → message 1: "RE: Nieuw bericht via website Contact praktijk Nijdam"
    from: Assistente Praktijk Nijdam <assistente@praktijknijdam.nl>  |  Mon, 24 Jan 2022

guard verification (try to overwrite saved secret with garbage):
POST /api/cockpit/connectors/google/oauth/start
  body: {client_id: "550556174730-x.apps.googleusercontent.com", client_secret: "ab", approval: "Akkoord"}
  → status: blocked, reason: "Refusing to overwrite saved Google client_secret with a value shorter than 8 characters."
disk verification:
  /workspace/.secrets/google_oauth_client.json client_secret length: 35  (unchanged)
```

## Operationele notes

- **Voor nieuwe Google connector gebruikers**: de default scope-set is nu breed (gmail readonly+send+modify + drive metadata+file). Schaal het terug per workspace door custom scopes in de `start` call mee te geven of via een nieuw preset in `GOOGLE_SCOPE_PRESETS`.
- **Voor scope-uitbreidingen later**: voeg de scope toe aan `DEFAULT_GOOGLE_SCOPES` of een preset, registreer hem in Google Cloud Console OAuth consent screen (anders strip Google hem stilzwijgend), en doe daarna een re-login. De cockpit ziet automatisch de missing scope via `gmail_status.missing_capability_scopes` en toont de re-login banner.
- **Voor restricted/sensitive scopes** in production-mode Google Cloud apps: Google vereist verificatie (kan weken duren). Houd de app in "Testing" mode en voeg de relevante Google-accounts toe als test users — geen verificatie nodig.
- **Voor pending OAuth codes**: deze verlopen na 10 minuten (zie `google_oauth_pending_code.json.expires_at`). Als een exchange faalt, check eerst of de code nog geldig is via `/api/cockpit/connectors/google/oauth/status` `.pending_code.expired`.

## Guardrails gerespecteerd

- Geen client_secret of access_token in git, JSONL, memory of cockpit chat-context. Secret werd via `docker exec -i` stdin geleverd, niet via command-line args of bash history.
- Geen `data/chromadb/*` of `wintrip_brain/*` binaries gecommit.
- Geen niet-gerelateerde untracked files (`.roo/`, `Agents.md`, `chaosclean/`, etc.) meegenomen.
- `Akkoord` is en blijft enige approval-poort voor mutating/private tools. Geen consent bypass.
- Geen claims rondom consciousness/sentience; alle UI-labels operationeel ("Re-connect Google", "Google scopes ontbreken").
- De rauwe Google 403 JSON blijft beschikbaar in `reason` voor debugging, maar wordt niet meer als enige signaal aan de UI getoond.

## Wat een volgende sessie kan oppakken

1. **Self-test via Agent Workspace UI**: bij elke chat-call met agentische sessie zien de gebruikers nu live de re_login_required banner verschijnen als een Google tool faalt. Een one-click "Re-authorize"-knop die `/api/cockpit/connectors/google/oauth/start` automatisch triggert (in plaats van naar de Connectors-tab te navigeren) zou nog directer zijn. Vereist client-config aanwezig zijn en gebruiker direct toegang tot een browser.
2. **Per-tool minimum scope advertising**: `agent_tools.py` zou voor élke Google-tool zijn `required_scope` kunnen exposen in de tool-schema, zodat het LLM-planner en de cockpit kunnen filteren op "alleen tools waarvoor we capability hebben".
3. **Token-rotation logging**: een audit-trail in de cockpit van wanneer tokens vernieuwd/uitgewisseld werden, met de scope-set per exchange, zou diagnose van soortgelijke incidenten in de toekomst sneller maken (zonder ooit de secret te tonen).
4. **Drive + Calendar tooling**: alle 5 scopes zijn nu gegrant. Andere Google-tools (`google_drive_list`, `drive_upload_text`, calendar lookup) kunnen nu via dezelfde route gepland worden zonder additionele OAuth setup.
5. **Generaliseer error-detection naar andere connectors**: hetzelfde `re_login_required`/`missing_scope` patroon kan toegevoegd worden voor GitHub, Slack, OpenAI ChatGPT browser, etc. Maakt een uniform "auth-broken" UX-pad mogelijk.

## Referenties

- Cline-grade levering: [HANDOFF_CLINE_GRADE_AGENTIC_DELIVERED_2026-05-18.md](HANDOFF_CLINE_GRADE_AGENTIC_DELIVERED_2026-05-18.md)
- Origineel ontwerp: [HANDOFF_CLINE_AGENTIC_POWER_TAURI_UI_2026-05-17.md](HANDOFF_CLINE_AGENTIC_POWER_TAURI_UI_2026-05-17.md)
- Originele bug-rapport: gebruikers chat-output met `gmail_search(error)` en 403 JSON
- AGENTS.md guardrails: [AGENTS.md](AGENTS.md)
- Shared runtime context: [OUROBOROS_IDE_CONTEXT.md](OUROBOROS_IDE_CONTEXT.md)
