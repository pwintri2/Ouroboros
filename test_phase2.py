import os
import sys
from controller.knowledge_base import KnowledgeBase
from controller.reflector import Reflector

def run_test():
    print("🚀 Starting Phase 2 Integration Test (Reflector Loop)...")
    
    # 1. Initialiseer Hippocampus en Reflector
    kb = KnowledgeBase()
    reflector = Reflector(kb=kb)
    
    # 2. Creëer een fake 'failure' output trace om de reflector te testen
    fake_docker_error = """
    Executing command...
    Error: Permission denied while trying to connect to the docker API at unix:///var/run/docker.sock.
    Operation not permitted. 
    Wintrip kon de taak niet voltooien in de zandbak.
    """
    
    # 3. Voer evaluate_action uit (verwacht is deterministische 'failure' opslag)
    print("\n[1] Evalueren en opslaan van actie in Hippocampus...")
    eval_result = reflector.evaluate_action(
        task_name="Docker Sandbox Mount",
        result_raw_output=fake_docker_error,
        expected_outcome="Succesvolle uitvoering van script test_phase1.py in de deamon."
    )
    
    print(f"--> Evaluatie type: {eval_result['type']}")
    print(f"--> Inzicht opgeslagen: {eval_result['stored']}")

    # 4. Controle via query: Retrieve it successfully from ChromaDB & verify it answers follow-up
    print("\n[2] Zoeken naar de opgeslagen failure-reflectie (Follow-up Query)...")
    results = kb.search_reflections("Waarom is de Docker Sandbox Mount mislukt?", n_results=2, max_distance=1.6)
    
    print("\n[3] Resultaten (Reflector Validatie):")
    if not results:
        print("❌ GEEN RESULTATEN GEVONDEN!")
        sys.exit(1)
        
    for idx, r in enumerate(results):
        metadata = r['metadata']
        print(f"#{idx+1} Score: {r['s_final']:.2f}")
        print(f"    Type: {metadata.get('type')}")
        print(f"    Tags: {metadata.get('tags')}")
        print(f"    Content: {r['content'][:120]}...")
        
    # Check if we successfully got our reflection back as top hit
    top_hit_type = results[0]['metadata'].get('type')
    
    if top_hit_type == 'failure':
        print("\n✅ TEST GESLAAGD! Reflector failure succesvol herinnerd voor opvolgende vragen.")
        sys.exit(0)
    else:
        print(f"\n❌ TEST MISLUKT! Returntype was '{top_hit_type}' in plaats van 'failure' of niet gevonden.")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
