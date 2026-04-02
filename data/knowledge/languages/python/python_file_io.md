# Python File I/O

Informatie over het veilig lezen en schrijven van bestanden met Python.

## Pathlib voor Padbeheer
Gebruik altijd de `pathlib` module voor paden in plaats van handmatige string-manipulatie (zoals `os.path.join`).

```python
from pathlib import Path

# Pad definiëren
config_path = Path("data/config.json")

# Bestaat het bestand?
if config_path.exists():
    print("Gevonden!")
```

## Veilig Bestanden Lezen en Schrijven
Gebruik altijd een context-manager (`with` statement) om bestanden correct te openen en te sluiten.

```python
# Schrijven
data = "Hello, Wintrip!"
Path("output.txt").write_text(data, encoding="utf-8")

# Lezen
content = Path("output.txt").read_text(encoding="utf-8")
```

## Werken met JSON en CSV
Voor gestructureerde data zijn JSON en CSV de standaardformaten.

```python
import json
import csv

# JSON schrijven
config = {"theme": "dark", "version": 2}
with open("config.json", "w") as f:
    json.dump(config, f, indent=4)

# CSV lezen
with open("data.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(row["name"])
```

## Encoding en Veiligheid
* **Encoding**: Gebruik altijd `utf-8` bij het openen van tekstbestanden om compatibiliteitsproblemen te voorkomen.
* **Pad-veiligheid**: Valideer dat paden binnen de toegestane mappen (sandbox) vallen en gebruik `.resolve()` om symlinks en relatieve paden te controleren.
* **Fouten**: Vang `OSError`, `PermissionError` en `IOError` op bij bestandsoperaties.
