# Python Basics

Python is een veelzijdige, high-level programmeertaal die de nadruk legt op leesbaarheid van code.

## Syntax en Variabelen
Python gebruikt inspringing (indentation) om codeblokken te definiëren in plaats van accolades.

```python
# Variabelen zijn dynamisch getypeerd
name = "Wintrip"
version = 1.0
is_active = True
```

## Functies en Classes
Functies worden gedefinieerd met `def` en classes met `class`.

```python
def begroeting(user):
    return f"Hallo, {user}!"

class Agent:
    def __init__(self, name):
        self.name = name
    
    def act(self):
        print(f"{self.name} voert actie uit.")
```

## Imports en Error Handling
Gebruik `import` voor modules en `try-except` voor foutafhandeling.

```python
import os
import json

try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    print("Configuratiebestand niet gevonden.")
```

## Virtual Environments (VENV)
Het is best-practice om voor elk project een eigen virtuele omgeving te gebruiken om dependency-conflicten te voorkomen.
* Creatie: `python -m venv .venv`
* Activatie (macOS): `source .venv/bin/activate`

## Best Practices
* Gebruik duidelijke namen voor variabelen en functies (snake_case).
* Schrijf docstrings voor functies en classes.
* Houd scripts klein en modulair.
* Gebruik `if __name__ == "__main__":` om scripts uitvoerbaar te maken zonder neveneffecten bij imports.
