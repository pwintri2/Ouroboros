import asyncio
import docker
import os
import tempfile
import time
from dotenv import load_dotenv
from controller.reflector import Reflector

load_dotenv()

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
            # Veilige datatunnel via .env (geen hardcoded paden)
            host_data_dir = os.getenv(
                "SANDBOX_DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "speeltuin")
            )
            os.makedirs(host_data_dir, exist_ok=True)

            cpu_quota = int(os.getenv("SANDBOX_CPU_QUOTA", "50000"))   # 50% van 1 core
            mem_limit = os.getenv("SANDBOX_MEM_LIMIT", "256m")

            print("⚙️  [Sandbox]: Container wordt opgestart en code wordt uitgevoerd...")
            container = self.client.containers.run(
                image="python:3.10-slim",
                command="python /script.py",
                volumes={
                    script_path: {'bind': '/script.py', 'mode': 'ro'},
                    host_data_dir: {'bind': '/app/data', 'mode': 'rw'}
                },
                detach=True,
                network_disabled=True,
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                read_only=True,
                tmpfs={'/tmp': 'size=64m,mode=1777'},
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
                
        # Integratie: Sla traces op in geheugen via Reflector (zowel fouten als successen)
        if not self.reflector:
            self.reflector = Reflector()
        if result_dict["status"] in ["error", "timeout"]:
            print(f"🪞 [Sandbox]: Failover log opslaan voor latere inspectie...")
            self.reflector.evaluate_action(
                task_name=f"{task_name} ({result_dict['error_type']})",
                result_raw_output=result_dict["logs"],
                expected_outcome=f"Exit code 0 binnen {timeout} seconden"
            )
        elif result_dict["status"] == "success":
            # Autopoiesis: sla succesvolle inzichten ook op in Hippocampus
            self.reflector.evaluate_action(
                task_name=task_name,
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

    async def arun_python_code(self, code: str, timeout: int = 15, task_name: str = "Async Sandbox Execution") -> dict:
        """
        Async wrapper rondom run_python_code zodat meerdere sandbox-runs
        gelijktijdig kunnen draaien binnen een asyncio event loop (DreamCycle).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run_python_code(code, timeout=timeout, return_dict=True, task_name=task_name)
        )
