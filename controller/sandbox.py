import docker
import os
import tempfile
import time
import requests
from controller.reflector import Reflector

class SandboxExecutor:
    def __init__(self):
        print("🛡️  [Sandbox]: Initialisatie van de Virtuele Quarantaine...")
        self.reflector = None
        try:
            self.client = docker.from_env()
            self.client.ping()
            print("✅ [Sandbox]: Docker connectie succesvol. De kooi is klaar.")
            self._ensure_image("python:3.10-slim")
        except Exception as e:
            print(f"❌ [Sandbox FOUT]: Kan Docker niet bereiken. Draait Docker Desktop? Error: {e}")
            self.client = None

    def _ensure_image(self, image_name):
        try:
            self.client.images.get(image_name)
        except docker.errors.ImageNotFound:
            print(f"⏳ [Sandbox]: Basis image '{image_name}' wordt gedownload. Dit duurt even...")
            self.client.images.pull(image_name)
            print(f"✅ [Sandbox]: Image '{image_name}' klaar voor gebruik.")

    def run_python_code(self, code: str, timeout: int = 15, return_dict: bool = False, task_name: str = "Sandbox Execution"):
        """
        Draait AI-gegeneerde Python code in een tijdelijke, geïsoleerde container.
        """
        if not self.client:
            msg = "FOUT: Sandbox (Docker) is niet beschikbaar of draait niet."
            return {"status": "error", "logs": msg, "exit_code": -1, "timed_out": False, "error_type": "docker_offline", "duration_seconds": 0.0} if return_dict else msg

        print("\n" + "="*40)
        print("🚧 [Sandbox]: AI Code wordt in quarantaine geplaatst...")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_script:
            temp_script.write(code)
            script_path = temp_script.name

        container = None
        started_at = time.time()
        
        result_dict = {
            "status": "pending",
            "logs": "",
            "exit_code": -1,
            "timed_out": False,
            "error_type": None,
            "duration_seconds": 0.0
        }
        
        try:
            print("⚙️  [Sandbox]: Container wordt opgestart en code wordt uitgevoerd...")
            container = self.client.containers.run(
                image="python:3.10-slim",
                command=f"python /script.py",
                volumes={script_path: {'bind': '/script.py', 'mode': 'ro'}},
                detach=True,
                network_disabled=False,
                mem_limit="512m",
            )
            
            # Wacht op de container met harde read timeout protectie
            result = container.wait(timeout=timeout)
            result_dict["exit_code"] = result.get('StatusCode', -1)
            result_dict["logs"] = container.logs().decode('utf-8', errors='replace')
            
            if result_dict["exit_code"] == 0:
                result_dict["status"] = "success"
                print("✅ [Sandbox]: Code succesvol uitgevoerd zonder errors.")
            else:
                result_dict["status"] = "error"
                result_dict["error_type"] = "runtime_error"
                print("⚠️ [Sandbox]: Code is gecrasht in de container!")
                
        except Exception as e:
            error_str = str(e).lower()
            if "timed out" in error_str or "timeout" in error_str:
                result_dict["status"] = "timeout"
                result_dict["timed_out"] = True
                result_dict["error_type"] = "ReadTimeout"
                print(f"⏳ [Sandbox]: Tijdslimiet ({timeout}s) verstreken! Oneindige loop of slow process. Container wordt getermineerd...")
                try:
                    container.kill()
                    result_dict["logs"] = container.logs().decode('utf-8', errors='replace')
                except Exception:
                    result_dict["logs"] = "[Time-out: Geen terminal logs beschikbaar na geforceerde stop]"
            else:
                result_dict["status"] = "error"
                result_dict["error_type"] = "fatal_sandbox_error"
                result_dict["logs"] = f"[SANDBOX FATAL ERROR]: {str(e)}"
                print(f"💥 [Sandbox KRIEKIE]: {str(e)}")
            
        finally:
            result_dict["duration_seconds"] = round(time.time() - started_at, 2)
            
            if container:
                try:
                    container.remove(force=True)
                    print("🗑️  [Sandbox]: Container vernietigd.")
                except Exception:
                    pass
                    
            if os.path.exists(script_path):
                os.remove(script_path)
                
        # Integratie: Sla falende traces op in geheugen via Reflector
        if result_dict["status"] in ["error", "timeout"]:
            if not self.reflector:
                self.reflector = Reflector()
            print(f"🪞 [Sandbox]: Failover log opslaan voor latere inspectie...")
            self.reflector.evaluate_action(
                task_name=f"{task_name} ({result_dict['error_type']})",
                result_raw_output=result_dict["logs"],
                expected_outcome=f"Exit code 0 binnen {timeout} seconden"
            )
            
        print("="*40 + "\n")
        
        # Compatibiliteitslaag zodat huidige aanroepende code via Virtual_team of router.py niet crasht
        if not return_dict:
            if result_dict["status"] == "success":
                return result_dict["logs"].strip()
            elif result_dict["status"] == "timeout":
                return f"[SANDBOX TIME-OUT na {result_dict['duration_seconds']}s]:\n{result_dict['logs']}".strip()
            else:
                return f"[SANDBOX ERROR (Code {result_dict['exit_code']})]:\n{result_dict['logs']}".strip()
                
        return result_dict
