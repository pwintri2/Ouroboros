import sys
import os

# Ensure the parent directory is in the path to resolve controller imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from controller.sandbox import SandboxExecutor
    
    print("[SMOKE TEST] Sandbox module succesvol geladen.")
    executor = SandboxExecutor()
    print("[SMOKE TEST] Sandbox API verbonden. We draaien nu code BINNEN een container OP de VPS!")
    
    test_code = "print('Hallo vanaf het diepste niveau (Docker-in-Docker op de VPS)!')"
    resultaat = executor.run_python_code(test_code, timeout=10)
    
    print("\n--- RESULTAAT VAN CODE EXECUTIE ---")
    print(resultaat)
    print("-----------------------------------")
    
except Exception as e:
    print(f"[SMOKE TEST ERROR] Fout opgetreden: {e}")
