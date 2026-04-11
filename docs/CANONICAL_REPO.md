# Canonical Repo Reference

## Hoofdmap voor actieve ontwikkeling
Gebruik altijd deze map als primaire WintripAI-repo:

```bash
/Users/philip/WintripAI
```

## Laatst gevalideerde build-locatie
De laatste echte build, Docker-validatie, `/agent/config` controle en milestone-commit zijn uitgevoerd vanuit:

```bash
/Users/philip/WintripAI
```

## Niet gebruiken als hoofdproject
Deze nested map is een legacy snapshot / dubbele projectkopie en is **niet** de canonieke werkbasis:

```bash
/Users/philip/WintripAI/wintripai
```

## Praktische regel
Start elke nieuwe sessie hier:

```bash
cd /Users/philip/WintripAI
```

## Werkbeleid
- Nieuwe code en commits alleen vanuit `/Users/philip/WintripAI`
- `wintripai/` alleen behandelen als referentie / archief
- Geen builds, tests of nieuwe frontend-implementatie starten vanuit de nested snapshot
- Runtime-data zoals `wintrip_brain/` niet onbedoeld committen

## Frontend-fase
De UI-opbouw start vanuit de canonieke repo en niet vanuit de nested snapshot.
