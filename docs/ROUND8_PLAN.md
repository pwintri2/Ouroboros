# WintripAI — ROUND8_PLAN

## Ronde 8: Real-Time Depth & Workflow Polish
**Datum:** 2026-04-12
**Status:** Gepland / gestart

## Doel
De UI minder demo-waardig en meer dagelijks bruikbaar maken, met nadruk op:
- echte live interactie
- betere werkflows
- meer afgeronde UX

## Scope

### 1. Echte token streaming
Vervang demo-SSE door echte backend/orchestrator stream waar mogelijk.

Werkpunten:
- stream endpoint uitbreiden
- partial token updates
- nette completion-state
- fallback bij stream errors

### 2. Chat persistence verdiepen
Maak chats meer first-class.

Werkpunten:
- actieve chat consistenter bewaren
- nieuwe berichten koppelen aan actieve chat
- history + current session beter laten samenwerken
- chattitel / context verbeteren

### 3. Search-result workflow verbeteren
Niet alleen hits tonen, maar ze ook bruikbaar maken.

Werkpunten:
- click-to-insert in chat
- memory hit details
- broncontext duidelijker
- betere lege/loading/error states

### 4. Persona UX polish
De persona tools zijn er, nu moeten ze netter.

Werkpunten:
- editor UX verbeteren
- foto preview strakker
- duidelijkere selected state
- confirm dialog voor delete

### 5. Diff/workflow polish
Diff moet professioneler voelen.

Werkpunten:
- betere actieve diff selectie
- duidelijkere statuslabels
- applied/rejected states netter
- file grouping / task grouping voorbereiden

### 6. Telemetry refinement
Nu vooral bruikbaar maken i.p.v. alleen aanwezig.

Werkpunten:
- duidelijkere live status
- betere signal hierarchy
- compactere informatiepresentatie
- eventueel mini historical state

## Verwachte uitkomst
Na deze ronde moet WintripAI duidelijk beter voelen als:
- echte mission-control werkplek
- dagelijkse cockpit
- minder prototype, meer tool
