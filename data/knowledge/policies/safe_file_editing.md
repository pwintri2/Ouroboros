# Safe File Editing

Richtlijnen voor het veilig en consistent bewerken van broncode en configuratiebestanden.

## Voorbereiding
* **Lees eerst**: Lees altijd de volledige inhoud (of de relevante scope) van het bestaande bestand voordat je wijzigingen voorstelt of uitvoert.
* **Begrijp Context**: Analyseer omliggende functies, imports en stijlconventies.

## Wijzigingsstrategie
* **Kleine Patches**: Voer wijzigingen uit in kleine, overzichtelijke stappen. Vermijd "mega-commits" die meerdere problemen tegelijk proberen op te lossen.
* **Minimale Impact**: Maak geen onnodige refactors of cosmetische wijzigingen die niet direct bijdragen aan het doel.
* **Architectuur**: Respecteer de bestaande architectuur en ontwerpkeuzes van het project. Introduceer geen nieuwe patronen tenzij expliciet gevraagd.

## Validatie en Logboek
* **Testen**: Test wijzigingen eerst in de sandbox omgeving voordat ze definitief worden gemaakt.
* **Logging**: Leg nauwkeurig vast wat er gewijzigd is, waarom de wijziging nodig was en wat de verwachte impact is.
* **Reproduceerbaarheid**: Zorg dat elke wijziging gedocumenteerd is zodat deze door anderen (of in een latere sessie) kan worden gevolgd of ongedaan gemaakt.
