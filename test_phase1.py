import os
import tempfile
import sys
from controller.knowledge_base import KnowledgeBase

def run_test():
    print("🚀 Starting Phase 1 Integration Test...")
    kb = KnowledgeBase()
    
    # Maak temp test bestanden aan
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f1:
        f1.write("Kennis over de firewall configuratie van Wintrip. Het wachtwoord is 12345.")
        user_mem_1 = f1.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f2:
        f2.write("Kennis over de favoriete koffie van Philip: Espresso.")
        user_mem_2 = f2.name
        
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f3:
        f3.write("Systeem documentatie: De backend maakt gebruik van FastAPI en Docker.")
        sys_doc_1 = f3.name

    print("\n[1] Ingesting files...")
    kb.ingest_file(user_mem_1)
    kb.ingest_file(user_mem_2)
    kb.ingest_file(sys_doc_1)
    
    print("\n[2] Executing search for 'Wintrip configuratie'")
    results = kb.search_detailed("Wintrip configuratie", n_results=3, max_distance=1.6)
    
    print("\n[3] Resultaten (S_final test):")
    if not results:
        print("❌ GEEN RESULTATEN GEVONDEN!")
    for idx, r in enumerate(results):
        print(f"#{idx+1} Score: {r['s_final']:.2f} | Type: {r['metadata'].get('type')} | Text: {r['content'][:60]}")
    
    # Cleanup
    os.remove(user_mem_1)
    os.remove(user_mem_2)
    os.remove(sys_doc_1)

    # Verifieer of user_memory correct prioriteit krijgt:
    if results and results[0]['metadata'].get('type') == 'user_memory':
        print("\n✅ TEST GESLAAGD! User_memory wint op basis van S_final hybride score.")
        sys.exit(0)
    else:
        print("\n❌ TEST MISLUKT! User_memory kreeg geen voorrang of fout in retrieval.")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
