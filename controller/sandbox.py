import asyncio
import docker
import os
import tempfile
import time
import requests
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Any, Optional, Sequence
from controller.reflector import Reflector

load_dotenv()

# ---------------------------------------------------------------------------
# Sandbox hardening defaults (Phase 7.X — wintrip-soc-008)
# ---------------------------------------------------------------------------
# Alle code-executie containers draaien met deze beveiligingslimieten.
# web_ingest en network-dependent tools geven allow_network=True mee.
_SANDBOX_DEFAULTS = {
    "image":           "python:3.10-slim",
    "network_disabled": True,           # netwerk standaard UIT (expliciet opt-in)
    "mem_limit":       "256m",          # geheugen hard cap
    "memswap_limit":   "256m",          # swap eveneens begrensd
    "cpu_period":      100_000,         # 100ms scheduling window
    "cpu_quota":       50_000,          # max 50% van één CPU-kern
    "pids_limit":      64,              # max 64 processen (fork-bomb preventie)
    "read_only":       True,            # rootfs read-only (schrijven alleen via volumes)
    "tmpfs":           {"/tmp": "size=64m,mode=1777"},  # writable /tmp in geheugen
    "security_opt":    ["no-new-privileges:true"],
    "detach":          True,
}

class SandboxExecutor:
    def __init__(self):
        print("🛡️  [Sandbox]: Initialisatie van de Virtuele Quarantaine...")
        self.reflector = Reflector()
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

    def run_python_code(self, code: str, timeout: int = 15, return_dict: bool = False,
                        task_name: str = "Sandbox Execution", allow_network: bool = False):
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
            # Bouw hardened container-configuratie op basis van _SANDBOX_DEFAULTS
            container_config = dict(_SANDBOX_DEFAULTS)
            container_config["command"] = "python /script.py"
            container_config["volumes"] = {
                script_path:    {"bind": "/script.py",  "mode": "ro"},
                host_data_dir:  {"bind": "/app/data",   "mode": "rw"},
            }
            # Netwerk: alleen inschakelen als de aanroeper dat expliciet vraagt
            # (bijv. web_ingest). Code-executie altijd netwerk-loos.
            container_config["network_disabled"] = not allow_network

            container = self.client.containers.run(**container_config)
            
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
        if self.reflector:
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

    async def arun_python_code(self, code: str, timeout: int = 15, return_dict: bool = True,
                               task_name: str = "Async Sandbox Execution",
                               allow_network: bool = False):
        """
        Async façade rond de sync Docker SDK. Elke run blijft een eigen hardened
        container gebruiken; asyncio versnelt alleen de host-orchestratie.
        """
        return await asyncio.to_thread(
            self.run_python_code,
            code,
            timeout,
            return_dict,
            task_name,
            allow_network,
        )

    async def run_time_dilated_dream(self, cycles: Sequence["DreamCycle"], **kwargs) -> dict[str, Any]:
        dilator = TimeDilationSandbox(executor=self, **kwargs)
        return await dilator.run_dream(cycles)


@dataclass(frozen=True)
class DreamCycle:
    name: str
    code: str
    timeout: int = 8
    allow_network: bool = False


class TimeDilationSandbox:
    """
    Async Dream Principle wrapper: many virtual IT-team iterations are scheduled
    concurrently while each physical execution remains Docker-isolated.
    """

    def __init__(
        self,
        executor: Optional[SandboxExecutor] = None,
        *,
        max_parallel: int = 3,
        virtual_time_scale: float = 3600.0,
        fail_fast: bool = True,
    ):
        self.executor = executor or SandboxExecutor()
        self.max_parallel = max(1, int(max_parallel))
        self.virtual_time_scale = max(1.0, float(virtual_time_scale))
        self.fail_fast = fail_fast

    async def _run_one(self, cycle: DreamCycle, semaphore: asyncio.Semaphore) -> dict[str, Any]:
        async with semaphore:
            started_at = time.perf_counter()
            result = await self.executor.arun_python_code(
                cycle.code,
                timeout=cycle.timeout,
                return_dict=True,
                task_name=f"DreamCycle:{cycle.name}",
                allow_network=cycle.allow_network,
            )
            physical_seconds = max(0.0, time.perf_counter() - started_at)
            return {
                "cycle": cycle.name,
                "status": result.get("status", "error"),
                "exit_code": result.get("exit_code", -1),
                "logs": result.get("logs", ""),
                "error_type": result.get("error_type"),
                "physical_seconds": round(physical_seconds, 4),
                "virtual_seconds": round(physical_seconds * self.virtual_time_scale, 4),
                "sandbox_isolated": True,
                "network_disabled": not cycle.allow_network,
            }

    async def run_dream(self, cycles: Sequence[DreamCycle]) -> dict[str, Any]:
        started_at = time.perf_counter()
        semaphore = asyncio.Semaphore(self.max_parallel)
        tasks = [asyncio.create_task(self._run_one(cycle, semaphore)) for cycle in cycles]
        results: list[dict[str, Any]] = []

        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            if self.fail_fast and result["status"] != "success":
                for pending in tasks:
                    if not pending.done():
                        pending.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                break

        physical_seconds = max(0.0, time.perf_counter() - started_at)
        return {
            "status": "success" if all(item["status"] == "success" for item in results) else "failed",
            "cycles_requested": len(cycles),
            "cycles_completed": len(results),
            "fail_fast": self.fail_fast,
            "max_parallel": self.max_parallel,
            "physical_seconds": round(physical_seconds, 4),
            "virtual_seconds": round(physical_seconds * self.virtual_time_scale, 4),
            "virtual_time_scale": self.virtual_time_scale,
            "sandbox_isolated": True,
            "results": results,
        }
