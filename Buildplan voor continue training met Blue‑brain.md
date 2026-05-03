Buildplan voor continue training met Blue‑brain

Deze buildplan beschrijft hoe de bestaande trainer‑pipeline in WintripAI (Ouroboros) kan worden aangepast zodat de twee trainers gebruikmaken van het script Blue‑brain.py om continu een eigen model te trainen. Het plan gaat uit van de huidige situatie zoals beschreven in de handover‑rapporten (LitGPT/Unsloth geïntegreerd, Trainer‑tab in de UI) en het beschikbare script Blue.py (het script kan ook Blue‑brain.py heten; hieronder wordt het aangeduid als Blue‑brain). Het doel is een onafhankelijk, hertrainbaar model binnen WintripAI zonder afhankelijkheid van externe modellen zoals Ollama.

1. Analyse van het bestaande script

Het script Blue.py genereert synthetische data die de activatieniveaus van 11 neuron‑types uit de Blue Brain‑paper representeren en traint een RandomForestClassifier om te voorspellen of het netwerk zich in een asynchrone of synchrone toestand bevindt. Belangrijke eigenschappen van dit script:

Data genereren: via sklearn.datasets.make_classification worden 10 000 monsters gecreëerd met 11 features en twee klassen. De features worden gelabeld met namen van de neuron‑types (e‑types) uit de Blue Brain‑paper.
Model: een RandomForestClassifier met 300 bomen en max‑depth 12. Het model wordt getraind en de nauwkeurigheid en het classificatierapport worden geprint. Een voorbeeldvoorspelling op een nieuw punt in de 11‑dimensionale ruimte wordt getoond.

Het script is momenteel bedoeld als demonstratie. Om het geschikt te maken voor integratie in de pipeline, moet het worden omgezet in een module met functies voor (1) datageneratie, (2) modeltraining, (3) evaluatie en (4) opslag van het getrainde model.

2. Architectuurwijzigingen
2.1 Nieuwe module blue_brain_adapter.py
Herstructureren van Blue‑brain.py: verplaats de logica van het script naar een module controller/blue_brain_adapter.py met functies zoals:
generate_dataset(n_samples: int, n_features: int, random_state: int) -> (X, y): maakt het 11‑dimensionale dataset aan. De parameter n_features is standaard 11 maar kan later worden geparameteriseerd.
train_model(X, y, hyperparams: dict) -> (model, metrics): traint een RandomForestClassifier met meegegeven hyperparameters (n_estimators, max_depth, random_state) en retourneert zowel het model als de evaluatiemetrieken (accuracy, classificatierapport als dict).
predict(model, X_new) -> y_pred: voorspelt de klasse voor nieuwe datapoints.
save_model(model, path: str): slaat het getrainde model op met bijvoorbeeld joblib.dump(); later kan dit model worden geladen voor inferentie of export.
load_model(path: str) -> model: laden van eerder getrainde modellen.
Afhankelijkheden: voeg scikit‑learn en joblib toe aan de lijst met vereiste Python‑pakketten (indien nog niet aanwezig). Zorg dat de virtuele omgeving voor de Blue‑brain trainer (.venv_blue_brain) deze bibliotheken bevat. Dit is apart van de bestaande venvs van LitGPT en Unsloth.
2.2 Uitbreiden van de trainer‑pipeline

De bestaande trainer‑pipeline bestaat uit adapters voor LitGPT en Unsloth, een job manager (controller/trainer_jobs.py), dataset builder (training_dataset_builder.py) en routes (trainer_pipeline_routes.py). Het plan is om Blue Brain toe te voegen als derde optie en de pipeline zodanig uit te breiden dat er non‑stop training mogelijk is.

Training‑adapter registreren: voeg in controller/main.py een nieuwe adapter blue_brain_adapter toe aan de afhankelijkheden. Het adapterobject kan dezelfde interface gebruiken als litgpt_adapter en unsloth_adapter:

from controller.blue_brain_adapter import BlueBrainTrainer
blue_brain_trainer = BlueBrainTrainer()

Deze klasse beheert datasetgeneratie, training en modelopslag.

Job‑type uitbreiding: in trainer_jobs.py definieer een nieuw jobtype 'blue_brain' met toestanden zoals DRAFT, APPROVED, TRAINING, COMPLETED, FAILED. Het job‑object bewaart hyperparameters en pad naar het opgeslagen model.
Routes aanpassen: update trainer_pipeline_routes.py zodat de bestaande endpoint POST /trainer/jobs een type‑parameter accepteert (bijv. 'litgpt', 'unsloth', 'blue_brain'). Voor Blue Brain zal de route create_training_job de BlueBrainTrainer aanroepen. Voorbeelden:
POST /trainer/jobs met JSON { "type": "blue_brain", "n_samples": 20000, "hyperparams": {"n_estimators": 300, "max_depth": 12} }
GET /trainer/dataset/preview?type=blue_brain&n_samples=1000 retourneert een subset van de 11‑dimensionale dataset als JSON, zodat de UI de kenmerken kan visualiseren.
Dataset preview: implementeer in training_dataset_builder.py een build_blue_brain_dataset() die de dataset aanmaakt via het adapter en een voorbeeld teruggeeft. Sla het volledige dataset op in een tijdelijke locatie (bijv. /workspace/tmp/blue_brain/), zodat de trainers niet telkens opnieuw de data hoeven te genereren bij een preview.
Niet‑stoppen training: voeg in trainer_jobs.py een scheduled task of background loop toe (bijv. asyncio.create_task) dat jobs met status APPROVED automatisch start zodra de vorige training is afgerond. Voor “non‑stop” training moet het systeem in een lus blijven doorlopen: na elke training worden de hyperparameters of het dataset aangepast (bijvoorbeeld een grotere dataset of andere random seed). Opties:
Cron‑achtige planning: gebruik APScheduler of celery beat om periodiek een train_blue_brain job aan te maken (bv. elk uur). Dit garandeert continue training.
Watcher op datasets: als het systeem real‑time data uit andere processen krijgt (bv. goedgekeurde records van gebruikers), kan een watcher de dataset uitbreiden en opnieuw trainen zodra er nieuwe records zijn.
Model artifacts: voeg in controller/model_artifacts.py ondersteuning toe voor Blue Brain modellen (bestandstype bijv. .joblib). De API kan via GET /trainer/jobs/<id>/artifact het model laten downloaden. Zorg dat de UI dit bestand kan ophalen of gebruiken voor inferentie.
2.3 UI‑updates
Trainer‑tab uitbreiden: in zowel de standalone UI (HTML) als de React‑UI moet een optie komen om een Blue Brain trainingjob te starten. Voeg een keuzemenu toe bij het maken van een nieuwe training waar “Blue Brain” kan worden geselecteerd en hyperparameters (n_samples, n_estimators, max_depth) kunnen worden ingevoerd.
Statusweergave: toon in de Trainer‑tab de voortgang van Blue Brain jobs (pending, training, completed). Na voltooiing moet de nauwkeurigheid en het classificatierapport worden weergegeven. Het classificatierapport kan als Markdown of JSON worden gerenderd.
Dataset preview UI: in de Context‑tab of onder het jobform kunnen visualisaties van de 11‑dimensionale dataset worden getoond, bijvoorbeeld een tabel met de e‑type features en labels. Omdat 11 dimensies veel zijn, kan een PCA‑reductie of een paar scatterplots worden gegenereerd (bijv. d3.js) om de gebruiker inzicht te geven in de data.
Configuratie van non‑stop training: bied de gebruiker een toggle aan om het continu hertrainen in te schakelen. Bijvoorbeeld: “Hertrain model elk uur” of “Hertrain wanneer er N nieuwe records zijn.” Deze instelling wordt opgeslagen bij het job‑object en bepaalt hoe de scheduler loopt.
3. Technische details
3.1 Virtuele omgeving

Gebruik een aparte virtuele omgeving voor Blue Brain om conflicten met de bestaande LitGPT/Unsloth dependencies te vermijden. Dit kan in de container worden aangemaakt bij het opstarten van de backend:

python3 -m venv /workspace/.venv_blue_brain
source /workspace/.venv_blue_brain/bin/activate
pip install -U scikit-learn joblib numpy

Het pad /workspace/.venv_blue_brain moet vervolgens worden ingesteld in blue_brain_adapter.py. Wanneer de container opnieuw wordt gebouwd, kan dit in een Dockerfile worden opgenomen zodat de venv persistent is.

3.2 Modellering en opslag
Gebruik joblib om het RandomForest‑model efficiënt op te slaan. Sla modellen op in een aparte map (/workspace/model_artifacts/blue_brain/) met bestandsnamen gebaseerd op job‑ID en datum (bijv. job_1234_20260501.joblib).
Voor continue training kan het model telkens worden overschreven of versiebeheer worden toegepast; voeg metadata toe (hyperparameters, timestamp, datasetgrootte) zodat de geschiedenis traceerbaar is.
3.3 API‑contracts en foutafhandeling
Valideer de inputparameters via Pydantic (bijv. n_samples moet > 1000 en n_estimators binnen een redelijke range) om uitputting van resources te voorkomen.
Geef duidelijke foutmeldingen terug via de API wanneer de Blue Brain trainer faalt (bv. wanneer scikit‑learn ontbreekt of datasetgeneratie mislukt).
3.4 Uitsluiten van Ollama en externe modellen
In model_artifacts.py en andere delen van het systeem hoeft geen export naar Ollama te worden geïmplementeerd. Exporteer in plaats daarvan alleen de joblib‑bestanden of maak een API dat de modellen intern beschikbaar stelt voor inference in WintripAI.
Verwijder of verberg UI‑opties die modellen naar Ollama exporteren wanneer het jobtype 'blue_brain' is.
4. Roadmap en fasering
Week 1 – Modulecreatie en backend:
Refactor Blue‑brain.py naar blue_brain_adapter.py met duidelijk gedefinieerde functies.
Maak virtuele omgeving .venv_blue_brain en documenteer installatie.
Implementeer nieuwe jobtype en adapter in backend (main.py, trainer_jobs.py, trainer_pipeline_routes.py).
Implementeer dataset preview endpoint en basis job lifecycle voor Blue Brain jobs.
Week 2 – UI‑integratie:
Voeg Blue Brain‑optie toe aan Trainer‑tab in zowel HTML als React.
Bouw formulieren voor hyperparameterinvoer en datasetgrootte.
Implementeer statusweergave en classificatieresultaat in de UI.
Implementeer dataset previewweergave (tabel of grafiek).
Week 3 – Non‑stop training:
Implementeer scheduler (bijv. APScheduler of Celery) om periodieke Blue Brain jobs te genereren.
Voeg configuratieopties toe voor interval of datasettriggering.
Zorg dat de backend jobs automatisch herstart zodra een model klaar is (lopend tot de gebruiker dit stopt).
Week 4 – Opschoning en documentatie:
Schrijf documentatie voor ontwikkelaars over het gebruik van blue_brain_adapter.py en het toevoegen van nieuwe trainers.
Schrijf handleidingen voor gebruikers over hoe ze een Blue Brain training kunnen starten en hoe non‑stop training werkt.
Test de pipeline volledig, inclusief foutafhandeling en resourcegebruik.
5. Conclusie

Door het Blue Brain‑script te modulariseren en te integreren als een volwaardige trainingoptie in de bestaande pipeline, ontstaat een flexibele en zelfvoorzienende trainingsomgeving binnen WintripAI. De aanbevolen aanpassingen zorgen ervoor dat de twee trainers (LitGPT/Unsloth) zelfstandig Blue Brain kunnen aanroepen of zelfs vervangen wanneer uitsluitend Blue Brain‑gebaseerde modellen gewenst zijn. Door non‑stop training via een scheduler te implementeren, blijft het model continu up‑to‑date met nieuwe data of parameters. Externe modellen zoals Ollama worden buiten beschouwing gelaten, waardoor de focus volledig op het eigen WintripAI‑ecosysteem ligt.