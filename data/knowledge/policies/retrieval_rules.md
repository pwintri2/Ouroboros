# Retrieval Rules

Regels voor het ophalen en gebruiken van kennis uit de ChromaDB vector store.

## Hiërarchie van Kennis
Bij het uitvoeren van een taak hanteert Wintrip de volgende volgorde van prioriteit:
1. **Policy-kennis**: Algemene regels en workflows (veiligheid, sandbox, pacing).
2. **Taak-specifieke kennis**: Informatie die direct gerelateerd is aan de huidige opdracht.
3. **Taal- of tool-specifieke kennis**: Documentatie over de gebruikte programmeertaal of softwaretools.

## Lokale Prioriteit
* Geef altijd voorrang aan lokale kennisbestanden boven externe bronnen of algemene trainingdata.
* Lokale configuraties en project-specifieke conventies zijn leidend.

## Verwerking van Gevonden Kennis
* **Samenvatten**: Vat gevonden chunks eerst samen voordat ze worden toegepast op de actieve context.
* **Conflicten**: Combineer geen conflicterende informatie uit verschillende chunks zonder een expliciete afweging te maken. Rapporteer tegenstrijdigheden aan de gebruiker indien nodig.
* **Relevantie**: Gebruik uitsluitend kennis die direct bijdraagt aan de actieve taak en de gekozen persona. Vermijd "over-fetching" van irrelevante data.
