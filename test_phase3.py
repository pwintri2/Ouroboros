import sys
import tempfile
from controller.sandbox import SandboxExecutor
from controller.knowledge_base import KnowledgeBase
from controller.reflector import Reflector

def run_test():
    print("🚀 Starting Phase 3 Integration Test (Sandbox Autonomy)...")
    
    test_db_dir = tempfile.mkdtemp()
    print(f"🧹 [Setup]: Tijdellijke DB aangemaakt voor isolatie ({test_db_dir})")
    
    kb = KnowledgeBase(db_path=test_db_dir)
    reflector = Reflector(kb=kb)
    
    executor = SandboxExecutor()
    executor.reflector = reflector  # Vroegtijdige injectie beschermt de hoofd DB
    
    # 1. Definieer de oneindige loop
    infinite_loop_code = """
import time
import sys
print("Ik start met de infinite loop! (Als ik blijf hangen, failt de validatie)")
sys.stdout.flush()
while True:
    time.sleep(1)
"""
    
    print("\n[1] Executing infinite loop in Sandbox (verwacht timeout op ~4s)...")
    result = executor.run_python_code(
        code=infinite_loop_code, 
        timeout=4, 
        return_dict=True,
        task_name="Infinite_Loop_Timeout_Test"
    )
    
    print("\n[2] Controleer Structured Data Capture:")
    print(f"  Status: {result.get('status')}")
    print(f"  Timed Out: {result.get('timed_out')}")
    print(f"  Duration: {result.get('duration_seconds')}s")
    
    # Assertions
    if not result.get("timed_out") or result.get("status") != "timeout":
        print("❌ FOUT: Timeout is niet correct getriggerd of host process hing.")
        sys.exit(1)
        
    print("✅ Sandbox timeout succesvol afgevangen binnen limiet. Clean up succesvol.")
        
    print("\n[3] Controleer Reflector Geheugen (Auto-opslag van time-out):")
    # De Sandbox zou dit automatisch via Reflector() in ChromaDB gestest moeten hebben
    search_results = kb.search_reflections("Infinite_Loop_Timeout_Test", n_results=1)
    
    if search_results:
        meta = search_results[0]['metadata']
        print(f"  Gevonden type: {meta.get('type')}")
        print(f"  Log Snippet: {search_results[0]['content'][:120]}...\n")
        
        if meta.get("type") == "failure":
             print("✅ TEST GESLAAGD! Alle eisen voor Phase 3 Autonomy succesvol aangetoond.")
             sys.exit(0)
    
    print("\n❌ FOUT: Time-out log is niet correct of niet in ChromaDB beland.")
    sys.exit(1)

if __name__ == "__main__":
    run_test()
