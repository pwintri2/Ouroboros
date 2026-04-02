import sys
import tempfile
from controller.router import AIRouter

def run_test():
    print("🚀 Starting Phase 4 Integration Test (OODA Routing)...")
    
    test_db_dir = tempfile.mkdtemp()
    print(f"🧹 [Setup]: Tijdellijke DB aangemaakt voor isolatie ({test_db_dir})")
    
    # 1. Start router in veilige, geïsoleerde staat (geen LLM nodig voor pure routing test)
    router = AIRouter(db_path=test_db_dir)
    
    # 2. Mock de MacAutomator call om een crash in 'Act' fase te forceren 
    # (Zodat we de Reflect fase kunnen verifiëren zonder echte host-apps te sluiten/openen)
    def mock_open_app(app_name):
        print(f"   [Mock Action]: Probeer '{app_name}' te openen...")
        raise PermissionError(f"Mock access denied to {app_name}")
        
    router.automator.open_app = mock_open_app
    
    # === START OODA LOOP ===
    print("\n[OODA CYCLE]: Sending Intent 'open Xcode'")
    # Hier loopt het via route_request: Observe(Vindt niets in tempDB) -> Deliberate(Detect_intent) -> Act(Execution) -> Reflect(Crash)
    answer = router.route_request("open Xcode")
    
    print("\n[1] Check Action Return Values (Non-Blocking Flow)")
    print(f"--> Router Answer: {answer}")
    
    # Assert return message to not crash the main thread, but return safe string
    if "is onverwacht gecrasht" not in answer and "FOUT" not in answer:
        print("❌ FOUT: De request crashte hard in de hoofdthread in plaats van veilig afgehandeld te worden.")
        sys.exit(1)
        
    print("✅ Act is veilig afgehandeld. Request is niet afgekapt maar correct geserveerd.")
    
    print("\n[2] Check Reflector (Auto Memory Pipeline)")
    results = router.brain.search_reflections("mock access denied")
    
    if not results:
        print("❌ FOUT: Reflector werd niet autonoom aangeroepen na action crash!")
        sys.exit(1)
        
    meta = results[0]['metadata']
    content = results[0]['content'].lower()
    print(f"   Reflector Type: {meta.get('type')}")
    print(f"   Snippet: {content[:100]}")
    
    if meta.get("type") == "failure" and "xcode" in content:
        print("\n✅ TEST GESLAAGD! Observe -> Deliberate -> Act -> Reflect routing werkt 100%.")
        sys.exit(0)
    else:
        print("❌ FOUT: Foutieve taxonomie in Reflector log na routing.")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
