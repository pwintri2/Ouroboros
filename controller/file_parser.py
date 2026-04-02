import os

def read_local_file(filename: str) -> str:
    """
    Veilige bestandslezer voor ongestructureerde documenten.
    Voorkomt Path Traversal door strikt te controleren op de 'data' map.
    """
    # Definieer de absolute basis-map
    # We gebruiken de locatie van dit script om de data-map in de parent dir te vinden.
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    
    # Maak het volledige doelpad en resolve naar een absoluut pad (lost ../ op)
    target_path = os.path.abspath(os.path.join(base_dir, filename))
    
    # VEILIGHEIDSREGEL: Controleer of het doelpad begint met de base_dir
    # Dit blokkeert pogingen om buiten de 'data' map te treden.
    if not target_path.startswith(base_dir):
        return f"[VEILIGHEIDSFOUT] Onveilige bestandstoegang gedetecteerd naar '{filename}'. Alleen toegang tot de WintripAI/data map is toegestaan."
    
    # Controleer of het bestand daadwerkelijk bestaat
    if not os.path.isfile(target_path):
        return f"[FOUT] Bestand '{filename}' niet gevonden in de data-map."

    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"[LEESFOUT] Fout bij het inlezen van bestand: {str(e)}"

if __name__ == "__main__":
    # Testcase voor validatie
    print("--- Start File Parser Veiligheidstests ---")
    
    # Test 1: Onveilig (Path Traversal)
    print(f"Poging ../.env: {read_local_file('../.env')}")
    
    # Test 2: Niet-bestaand bestand
    print(f"Poging onbestaand.txt: {read_local_file('onbestaand.txt')}")
