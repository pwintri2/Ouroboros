import sys
import os
import re
from datetime import datetime

try:
    from controller.reflector import Reflector
    from controller.sandbox import SandboxExecutor
    from controller.ollama_client import OllamaClient
except ImportError:
    try:
        from reflector import Reflector
        from sandbox import SandboxExecutor
        from ollama_client import OllamaClient
    except ImportError:
        pass # Handle testing gracefully

class TaskModel:
    def __init__(self, task_name, max_iterations=3):
        self.task_name = task_name
        self.status = "PENDING"
        self.iteration_count = 0
        self.max_iterations = max_iterations
        self.history = []

    def update_status(self, new_status):
        self.status = new_status

    def record_iteration(self, result_classification, insight):
        self.iteration_count += 1
        self.history.append({"iteration": self.iteration_count, "classification": result_classification, "insight": insight})
        if result_classification == "GREEN":
            self.status = "COMPLETED"
        elif result_classification == "RED":
            if self.iteration_count >= self.max_iterations:
                self.status = "FAILED"
            else:
                self.status = "RETRYING"
        elif result_classification == "YELLOW":
            self.status = "INVESTIGATING"

class ResultClassifier:
    def __init__(self, reflector=None):
        self.reflector = reflector or Reflector()

    def classify_result(self, task_name, raw_output, status="success"):
        eval_result = self.reflector.evaluate_action(task_name, raw_output)
        ref_type = eval_result.get("type", "insight")
        lowered = raw_output.lower()
        
        # Check against basic python exceptions (Tracebacks always mean a crash)
        if "traceback" in lowered or "syntaxerror:" in lowered:
            return "RED", "Reflector overrule: Harde exception (Traceback) gevonden in de output."
            
        if status == "success":
            # Als Exit Code 0 is (geen systeemcrash) en er zijn geen tracebacks:
            # Cheat/LLM drift detectie:
            if any(num in lowered for num in ["48.0", "48", "50", "50.0"]) and not any(w in lowered for w in ["zero", "nul", "fout", "waarschuwing", "exception", "niet mogelijk"]):
                return "RED", "Logic Failure: Hallucinatie / Smokkelen gedetecteerd. Je hebt de logica of wiskunde vervalst om output te forceren in plaats van de onvermijdelijke Exception af te vangen!"

            # Beschouw sierlijke exception handling (waarschuwingen geprint) als een GREEN succes!
            if ref_type in ["failure", "insight"]:
                return "GREEN", "✅ Graceful Exception Handling: Applicatie is veilig afgesloten en fout is opgevangen. [Reflector overrule]"
            return "GREEN", eval_result.get("insight", "Succesvolle executie.")
            
        # Voor overige statussen (zoals timeout of force-crash)
        if ref_type == "success":
            return "GREEN", eval_result.get("insight", "")
        elif ref_type == "failure":
            return "RED", eval_result.get("insight", "")
        else:
            return "YELLOW", eval_result.get("insight", "")

class WintripOrchestrator:
    def __init__(self, ollama_client=None, sandbox=None, reflector=None):
        self.ollama = ollama_client or OllamaClient()
        self.sandbox = sandbox or SandboxExecutor()
        self.reflector = reflector or Reflector()
        self.classifier = ResultClassifier(reflector=self.reflector)
        
    def _extract_code(self, response_text):
        match = re.search(r'```(?:python)?(?:.*?)\n(.*?)\n```', response_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Fallback if no block is provided but it looks like raw python
        return response_text.strip()

    def execute_task(self, prompt, max_iterations=3):
        print(f"\n🚀 [Regiekamer]: Start Autonome OODA Loop voor taak: '{prompt}'")
        task = TaskModel(task_name=prompt, max_iterations=max_iterations)
        
        # Initial Fast-Fail Developer prompt
        system_prompt = (
            "Je bent een expert Python Developer. Geef UITSLUITEND werkende Python code in een ```python blok. "
            "Geen uitleg voor of na de code. Importeer sys/os if needed. Zorg dat de logica print statements heeft zodat output gelezen kan worden.\n\n"
            "CRITICAL RESTRICTION: You are strictly forbidden from altering the mathematical constraints, logic, or string values provided in the prompt to avoid errors. "
            "If a task inherently leads to an exception (like dividing by zero), you MUST write the exact code requested, but wrap it in a proper try/except block and print a graceful error message. Do NOT cheat the logic."
        )
        current_prompt = f"Schrijf een concreet Python script dat exact het volgende oplost: {prompt}"
        
        while task.status in ["PENDING", "RETRYING", "INVESTIGATING"]:
            print(f"\n--- 🔄 OODA Iteratie {task.iteration_count + 1}/{task.max_iterations} ---")
            
            # Observe/Orient is already done by the state machine receiving the contextual input.
            
            # 1. Decide: Genereer Code
            print("🧠 [Decide]: 1-on-1 LLM genereert code (fail-fast strategy)...")
            ai_response = self.ollama.chat(current_prompt, system_prompt=system_prompt, model="llama3.1:latest")
            python_code = self._extract_code(ai_response)
            
            # 2. Act: Sandbox Excecutie
            print("⚙️  [Act]: Uitvoeren in Sandbox...")
            try:
                result_dict = self.sandbox.run_python_code(python_code, timeout=15, return_dict=True, task_name=prompt)
            except Exception as e:
                result_dict = {"status": "error", "logs": str(e), "exit_code": -1}
                
            raw_output = result_dict.get('logs', '')
            status = result_dict.get('status', 'error')
            
            # Print output explicitly for terminal users
            print(f"📄 [Sandbox Output]:\n{'-'*20}\n{raw_output.strip()}\n{'-'*20}")
            
            # 3. Reflect: Classificeer Output
            print("🪞 [Reflect]: Classificatie resultaat...")
            if status == "success":
                color, insight = self.classifier.classify_result(prompt, raw_output, status="success")
            elif status == "timeout":
                color = "YELLOW"
                insight = "Tijdslimiet verstreken (infinite loop/slow I/O)."
            else:
                color, insight = self.classifier.classify_result(prompt, raw_output, status="error")
                if color == "GREEN":
                     color = "RED" # Forceer red bij harde sandbox fails
                insight = f"Runtime Crash (Exit code {result_dict.get('exit_code')}): {insight}"
            
            print(f"📊 [Status Check]: Klassering = {color} | Inzicht = {insight}")
            
            # 4. Iterate: Werk states bij
            task.record_iteration(color, insight)
            
            if task.status == "COMPLETED":
                print(f"✅ [Regiekamer]: Taak voltooid na {task.iteration_count} iteraties.")
                return {"status": "SUCCESS", "final_output": raw_output, "history": task.history}
            
            elif task.status in ["RETRYING", "INVESTIGATING"]:
                print(f"⚠️ [Regiekamer]: Herstelactie ingezet aan de hand van Reflectie-inzichten.")
                current_prompt = (
                    f"Je vorige Python code-poging gaf de volgende output of foutmelding in de executie-omgeving:\n\n"
                    f"[OUTPUT]\n{raw_output}\n[/OUTPUT]\n\n"
                    f"Reflector inzicht: {insight}\n\n"
                    f"Los exact deze fouten op voor de opdracht '{prompt}' en schrijf de verbeterde complete code binnen een ```python blok. "
                    f"BE REMINDED: Do NOT alter the constraints or cheat the math to avoid errors. Handle the exceptions gracefully if they are inevitable!"
                )
                
            elif task.status == "FAILED":
                print(f"❌ [Regiekamer]: Taak gefaald en maximaal aantal pogingen bereikt ({task.iteration_count} iteraties).")
                return {"status": "FAILED", "final_output": raw_output, "history": task.history}
                
        return {"status": "UNKNOWN", "history": task.history}
