# WintripAI UI / Feature Backlog

## Context
Deze backlog bewaart de open voorstellen en vervolgrichtingen na de huidige Mission Control basis.

Canonieke repo:
```text
/Users/philip/WintripAI
```

Web UI:
```text
/Users/philip/WintripAI/webui
```

## Huidige status
Reeds aanwezig:
- multi-agent backend basis
- Mission Control webui scaffold + blueprint layout
- Docker runtime / launcher
- Gemini orchestrator in Docker
- Ollama sub-agent runtime
- persona manager basis
- chat history basis
- diff staging basis
- telemetry basis
- upload/search/SSE demo basis

## Open voorstellen / volgende rondes

### 1. Echte token streaming
Doel:
- vervang demo-SSE door echte orchestrator/agent stream
- partial tokens tonen in chat
- nette overgang van `streaming` -> `collapsed`

Werkpunten:
- backend stream endpoint(s)
- frontend EventSource/WebSocket integration
- betere streaming status indicators

### 2. Persona bewerken / verwijderen
Doel:
- persona cards niet alleen aanmaken, maar ook aanpassen en verwijderen
- prompt, beschrijving, bronnen en foto beheren

Werkpunten:
- backend update/delete endpoints
- edit modal/panel in sidebar
- delete confirmation
- photo preview/replace flow verfijnen

### 3. Upload -> ingest -> retrieval verbeteren
Doel:
- bestanden vanuit composer echt onderdeel maken van de geheugenworkflow
- duidelijk tonen dat document in Hippocampus terechtkomt

Werkpunten:
- upload metadata uitbreiden
- ingest resultaat tonen in UI
- documenttype / tags / bronlabels
- resultaat direct terugvindbaar maken via search

### 4. Semantic search UX verbeteren
Doel:
- zoekresultaten rijker tonen dan alleen tekst
- metadata en broncontext zichtbaar maken

Werkpunten:
- result cards met metadata
- klikbare bron/interaction context
- mogelijk gecombineerde chat + memory search

### 5. Chat/session persistence verdiepen
Doel:
- duidelijk onderscheid tussen algemene chat, vergadertafel modus en actieve sessie
- chat history vollediger koppelen aan message timeline

Werkpunten:
- actieve chat persistenter maken
- betere threading
- timestamps / rolweergave verbeteren
- session restore UX

### 6. Diff workflow verdiepen
Doel:
- staged diffs professioneler maken
- meerdere diffs beter beheren

Werkpunten:
- diff queue verbeteren
- filteren per agent / task
- applied/rejected states duidelijker tonen
- mogelijk compare tabs / file grouping

### 7. Telemetry verdieping
Doel:
- meer echte runtime metrics tonen
- minder placeholder, meer observability

Werkpunten:
- container counts live
- latency/network details
- VPS metrics indien beschikbaar
- signal history / micro charts

### 8. Vergadertafel UX verbeteren
Doel:
- agenten aan tafel uitnodigen en hun rollen visueel duidelijk maken
- beter onderscheid tussen seated en available personas

Werkpunten:
- seated badges/cards
- actieve tafelweergave
- voorzitter samenvatting sterker koppelen aan seated agents

### 9. UX polish / consistency pass
Doel:
- Mission Control consistenter en rustiger maken
- blueprint look behouden maar interacties verfijnen

Werkpunten:
- spacing / typography polish
- states voor loading/error/empty
- consistent buttons/toggles/panels
- betere visual hierarchy

### 10. End-to-end productiseringsronde
Doel:
- launcher + backend + webui + providers betrouwbaar samen laten werken

Werkpunten:
- volledige live testflow
- foutmeldingen verbeteren
- startup robustness
- documentatie voor dagelijkse workflow

## Aanbevolen volgorde
1. Echte token streaming
2. Persona edit/delete
3. Upload -> ingest -> retrieval verbeteren
4. Semantic search UX
5. Chat/session persistence
6. Telemetry verdieping
7. UX polish

## Notitie
ChromaDB runtime data hoort niet standaard in gewone Git commits. Gebruik hiervoor liever:
- backup/snapshot strategie
- export/import workflow
- reproduceerbare ingest pipeline
