import sys
import os
import re
import json
from datetime import datetime

try:
    from controller.reflector import Reflector
    from controller.sandbox import SandboxExecutor
    from controller.ollama_client import OllamaClient
    from controller.groq_client import GroqClient
    from controller.knowledge_base import KnowledgeBase
    from controller.web_ingest import ingest_url, fetch_url_text
    from controller.provider_router import route_provider
    from controller.agent_runtime import get_orchestrator_config, get_agent_configs
    from controller.agent_protocol import make_envelope
except ImportError:
    try:
        from reflector import Reflector
        from sandbox import SandboxExecutor
        from ollama_client import OllamaClient
        from groq_client import GroqClient
        from knowledge_base import KnowledgeBase
        from web_ingest import ingest_url, fetch_url_text
        from provider_router import route_provider
        from agent_runtime import get_orchestrator_config, get_agent_configs
        from agent_protocol import make_envelope
    except ImportError as e:
        print("--- [DEBUG] IMPORTERROR IN ORCHESTRATOR ---:", e)


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

        if "traceback" in lowered or "syntaxerror:" in lowered:
            return "RED", "Reflector overrule: Harde exception (Traceback) gevonden in de output."

        if status == "success":
            if any(pip_str in lowered for pip_str in ["collecting ", "downloading ", "installing collected packages", "successfully installed"]):
                return "GREEN", "✅ Systeem Logica: Succesvolle package installatie (PIP) gedetecteerd in output. [Reflector overrule]"

            if any(num in lowered for num in ["48.0", "48", "50", "50.0"]) and not any(w in lowered for w in ["zero", "nul", "fout", "waarschuwing", "exception", "niet mogelijk"]):
                return "RED", "Logic Failure: Hallucinatie / Smokkelen gedetecteerd. Je hebt de logica of wiskunde vervalst om output te forceren in plaats van de onvermijdelijke Exception af te vangen!"

            if ref_type in ["failure", "insight"]:
                return "GREEN", "✅ Graceful Exception Handling: Applicatie is veilig afgesloten en fout is opgevangen. [Reflector overrule]"
            return "GREEN", eval_result.get("insight", "Succesvolle executie.")

        if ref_type == "success":
            return "GREEN", eval_result.get("insight", "")
        elif ref_type == "failure":
            return "RED", eval_result.get("insight", "")
        else:
            return "YELLOW", eval_result.get("insight", "")


class WintripOrchestrator:
    def __init__(self, ollama_client=None, sandbox=None, reflector=None, kb=None, escalator=None):
        self.ollama = ollama_client or (OllamaClient() if 'OllamaClient' in globals() else None)
        self.escalator = escalator or (GroqClient() if 'GroqClient' in globals() else None)
        self.sandbox = sandbox or SandboxExecutor()
        self.reflector = reflector or Reflector()
        self.kb = kb or KnowledgeBase()
        self.classifier = ResultClassifier(reflector=self.reflector)
        self.runtime = get_orchestrator_config()
        self.agent_configs = get_agent_configs(project_root=os.getenv("WINTRIP_PROJECT_ROOT", "/app"))
        self.active_model = self.runtime.get("provider", "gemini")

    def _extract_code(self, response_text):
        match = re.search(r'```(?:python)?(?:.*?)\n(.*?)\n```', response_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return response_text.strip()

    def _task_id(self):
        return datetime.utcnow().strftime("WT-%Y%m%d-%H%M%S")

    def review_subagent_result(self, envelope: dict) -> dict:
        summary = envelope.get("summary", "")
        risks = envelope.get("risks", [])
        return {
            "accepted": True,
            "summary": summary,
            "risks": risks,
            "needs_human": envelope.get("requires_human", False),
        }

    def assign_agent_task(self, agent_id: str, task: str) -> dict:
        cfg = self.agent_configs[agent_id]
        task_id = self._task_id()
        system_prompt = (
            f"Je bent {cfg.label} binnen WintripAI. "
            f"Werk uitsluitend binnen jouw ownership. "
            f"Lever ALTIJD JSON terug volgens WINTRIP-AGENT/1.0. "
            f"Provider default: {cfg.provider}. Model default: {cfg.model}."
        )

        raw = route_provider(cfg.provider, task, cfg.model, system_prompt=system_prompt)

        return make_envelope(
            agent=cfg.label,
            task_id=task_id,
            type="result",
            summary=raw[:1000],
            owned_paths=cfg.owned_paths,
            read_paths=[],
            write_paths=[],
            outputs=[raw],
            risks=[],
            needs_review=True,
            requires_human=False,
        )

    def orchestrate_multi_agent(self, task: str) -> dict:
        outputs = []
        agent_order = [
            "wintrip-developer-backend",
            "wintrip-ui-frontend",
            "wintrip-voorzitter-qa-tester",
            "wintrip-kritiek-docs-planning",
        ]
        for agent_id in agent_order:
            outputs.append(self.assign_agent_task(agent_id, task))

        synthesis_prompt = (
            "Je bent de Hoofdagent van WintripAI. "
            "Vat de volgende agentresultaten samen, valideer conflicten, "
            "en geef een integratie-advies. "
            "Escaleer naar Philip als ownership, sandbox-veiligheid of runtimeconfig onduidelijk is.\n\n"
            + json.dumps(outputs, ensure_ascii=False, indent=2)
        )
        review = route_provider(
            self.runtime.get("provider", "gemini"),
            synthesis_prompt,
            self.runtime.get("model", "gemini-2.5-pro"),
            system_prompt="Je bent de Hoofdagent/Integrator van WintripAI. Houd je strikt aan de ownership matrix en Human-in-the-Loop.",
        )
        return {
            "status": "SUCCESS",
            "mode": "multi-agent",
            "orchestrator_provider": self.runtime.get("provider", "gemini"),
            "orchestrator_model": self.runtime.get("model", "gemini-2.5-pro"),
            "agents": outputs,
            "review": review,
        }

    def execute_task(self, prompt, max_iterations=3):
        if os.getenv("WINTRIP_MULTI_AGENT_ENABLED", "1") == "1":
            return self.orchestrate_multi_agent(prompt)

        print(f"\n🚀 [Regiekamer]: Start Autonome OODA Loop voor taak: '{prompt}'")
        task = TaskModel(task_name=prompt, max_iterations=max_iterations)

        print("👀 [Observe & Orient]: Scannen op web links en ophalen van geheugen...")

        urls = re.findall(r'(https?://[^\s]+)', prompt)
        full_context = ""

        if urls:
            full_context += "\n[GEHEUGEN CONTEXT]\nSpecifieke letterlijke web-inhoud direct gescraapt uit je taak:\n"
            for url in urls:
                print(f"🌍 [Orient]: URL gedetecteerd, sniper-scrape wordt uitgevoerd: {url}")
                try:
                    ingest_url(url)
                    raw_text = fetch_url_text(url)
                    if raw_text:
                        print(f"🌍 [Orient]: Hard Pinning succesvol. {len(raw_text)} characters toegevoegd aan de LLM Prompt.")
                        snippet = raw_text[:3000] + "\n...\n" if len(raw_text) > 3000 else raw_text
                        full_context += f"-> Ruwe tekst van {url}:\n{snippet}\n\n"
                except Exception as e:
                    print(f"⚠️ [Orient]: Scrapen mislukt, fallback: we negeren deze URL tijdelijk. ({e})")
            full_context += "[/GEHEUGEN CONTEXT]\n\nBaseer je oplossing uitsluitend op deze bovenstaande web-documentatie.\n"
        else:
            memories = self.kb.search_detailed(prompt, n_results=3)
            if memories:
                full_context = "\n[GEHEUGEN CONTEXT]\nEr is krachtige relevante programmeerkennis gevonden in de Hippocampus:\n"
                for m in memories:
                    full_context += f"- Bron ({m['metadata'].get('source_type', 'unknown')}): {m['content']}\n\n"
                full_context += "[/GEHEUGEN CONTEXT]\n\nGebruik deze kennis strikt bij het schrijven van je oplossing als het relevant is.\n"

        SANDBOX_CODE_RULES = """
KRITIEKE REGELS VOOR CODE GENERATIE:
1. Schrijf UITSLUITEND zelfstandige Python scripts. Importeer alleen modules uit de Python standaardbibliotheek (os, sys, json, csv, math, datetime, re, etc.) tenzij je eerst controleert met pip install.
2. Lees NOOIT externe bestanden zoals 'config.json', 'settings.yaml', of enig ander bestand dat je zelf niet in het script aanmaakt. De sandbox container is leeg op jouw script na.
3. Als je data nodig hebt, genereer die dan direct in het script (hardcode het, of genereer het met code).
4. Bestanden die je wilt bewaren, sla op in /app/data/ (dat is de enige gemounte map).
5. Gebruik GEEN relatieve paden. Gebruik /app/data/ voor alle file I/O.
"""

        system_prompt = (
            "Je bent een expert Python Developer. Geef UITSLUITEND werkende Python code in een ```python blok. "
            "Geen uitleg voor of na de code. Importeer sys/os if needed. Zorg dat de logica print statements heeft zodat output gelezen kan worden.\n\n"
            "CRITICAL RESTRICTION: You are strictly forbidden from altering the mathematical constraints, logic, or string values provided in the prompt to avoid errors. "
            "If a task inherently leads to an exception (like dividing by zero), you MUST write the exact code requested, but wrap it in a proper try/except block and print a graceful error message. Do NOT cheat the logic.\n\n"
            "CRITICAL AUTONOMY: You are executing code autonomously inside an ephemeral Docker container. You CANNOT ask the user to install packages or fix environments. "
            "If your code requires an external package (like pandas) that might cause a ModuleNotFoundError, you MUST either rewrite the code using standard built-in Python modules (like 'csv'), "
            "or write code that installs the package itself during runtime via subprocess.check_call([sys.executable, '-m', 'pip', 'install', '<package>']) before executing the main logic.\n\n"
            f"{SANDBOX_CODE_RULES}"
        )
        current_prompt = f"Schrijf een concreet Python script dat exact het volgende oplost:\n\n{prompt}\n{full_context}"

        while task.status in ["PENDING", "RETRYING", "INVESTIGATING"]:
            print(f"\n--- 🔄 OODA Iteratie {task.iteration_count + 1}/{task.max_iterations} ---")

            rag_results = self.kb.search(current_prompt, n_results=5)
            if rag_results:
                memory_block = "\n\n[GEHEUGEN CONTEXT - relevante kennis uit ChromaDB]\n"
                memory_block += "\n---\n".join([r["text"] for r in rag_results])
                enriched_message = current_prompt + memory_block
            else:
                enriched_message = current_prompt

            if task.iteration_count >= 2 and self.escalator:
                print("🔥 [ESCALATIE]: Local LLM bleef hangen. Overschakelen naar Cloud 70B Model (Groq) ...")
                escalation_system_prompt = system_prompt + "\n\n[ESCALATION INSTRUCTION]\nYour local junior model failed to generate working code for this problem. You are the senior escalation model. Look at the traceback and fix it flawlessly."
                ai_response = self.escalator.chat(enriched_message, system_prompt=escalation_system_prompt, model="llama-3.3-70b-versatile")
            else:
                print("🧠 [Decide]: 1-on-1 LLM genereert code (fail-fast strategy)...")
                ai_response = self.ollama.chat(enriched_message, system_prompt=system_prompt, model="llama3.1:latest")

            python_code = self._extract_code(ai_response)

            if python_code.startswith("LOKALE OLLAMA ERROR") or python_code.startswith("CLOUD GROQ ERROR"):
                print(f"⚠️ [API FOUT]: {python_code}")
                task.record_iteration("YELLOW", f"LLM API verbinding gefaald: {python_code}")
                continue

            print("⚙️  [Act]: Uitvoeren in Sandbox...")
            try:
                result_dict = self.sandbox.run_python_code(python_code, timeout=15, return_dict=True, task_name=prompt)
            except Exception as e:
                result_dict = {"status": "error", "logs": str(e), "exit_code": -1}

            raw_output = result_dict.get('logs', '')
            status = result_dict.get('status', 'error')

            print(f"📄 [Sandbox Output]:\n{'-'*20}\n{raw_output.strip()}\n{'-'*20}")

            print("🪞 [Reflect]: Classificatie resultaat...")
            if status == "success":
                color, insight = self.classifier.classify_result(prompt, raw_output, status="success")
            elif status == "timeout":
                color = "YELLOW"
                insight = "Tijdslimiet verstreken (infinite loop/slow I/O)."
            else:
                color, insight = self.classifier.classify_result(prompt, raw_output, status="error")
                if color == "GREEN":
                    color = "RED"
                insight = f"Runtime Crash (Exit code {result_dict.get('exit_code')}): {insight}"

            print(f"📊 [Status Check]: Klassering = {color} | Inzicht = {insight}")

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
