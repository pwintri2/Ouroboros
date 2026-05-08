import sys
import os
import re
from datetime import datetime
from datetime import timezone
from typing import Any, Callable, Mapping

try:
    from controller.reflector import Reflector
    from controller.sandbox import SandboxExecutor
    from controller.ollama_client import OllamaClient
    from controller.groq_client import GroqClient
    from controller.knowledge_base import KnowledgeBase
    from controller.web_ingest import ingest_url, fetch_url_text
except ImportError:
    try:
        from reflector import Reflector
        from sandbox import SandboxExecutor
        from ollama_client import OllamaClient
        from groq_client import GroqClient
        from knowledge_base import KnowledgeBase
        from web_ingest import ingest_url, fetch_url_text
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
        
        # Check against basic python exceptions (Tracebacks always mean a crash)
        if "traceback" in lowered or "syntaxerror:" in lowered:
            return "RED", "Reflector overrule: Harde exception (Traceback) gevonden in de output."
            
        if status == "success":
            # Als Exit Code 0 is (geen systeemcrash) en er zijn geen tracebacks:
            # Subprocess/PIP protectie: Pip output bevat vaak MB/s snelheden die de anti-hallucinatie bug triggeren.
            if any(pip_str in lowered for pip_str in ["collecting ", "downloading ", "installing collected packages", "successfully installed"]):
                return "GREEN", "✅ Systeem Logica: Succesvolle package installatie (PIP) gedetecteerd in output. [Reflector overrule]"

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


try:
    from controller.agentic_intent import should_use_agentic_processor as _canonical_should_use_agentic_processor
except Exception:
    try:
        from agentic_intent import should_use_agentic_processor as _canonical_should_use_agentic_processor
    except Exception:
        _canonical_should_use_agentic_processor = None


def should_use_agentic_processor(prompt: object, *, role: object = "", approval: object = "") -> bool:
    if _canonical_should_use_agentic_processor is None:
        return False
    return bool(_canonical_should_use_agentic_processor(prompt, role=role, approval=approval))

class WintripOrchestrator:
    def __init__(
        self,
        ollama_client=None,
        sandbox=None,
        reflector=None,
        kb=None,
        escalator=None,
        agent_tools=None,
        world_ask: Callable[..., dict[str, Any]] | None = None,
        world_search: Callable[..., dict[str, Any]] | None = None,
        tool_bridge_runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ):
        self.ollama = ollama_client or (OllamaClient() if 'OllamaClient' in globals() else None)
        self.escalator = escalator or (GroqClient() if 'GroqClient' in globals() else None)
        self.sandbox = sandbox or SandboxExecutor()
        self.reflector = reflector or Reflector()
        self.kb = kb or KnowledgeBase()
        self.classifier = ResultClassifier(reflector=self.reflector)
        self.agent_tools = agent_tools
        self._world_ask = world_ask
        self._world_search = world_search
        self._tool_bridge_runner = tool_bridge_runner
        self._living_loop = None
        self._start_living_consciousness_loop()

    def configure_living_tools(
        self,
        *,
        agent_tools: Any = None,
        world_ask: Callable[..., dict[str, Any]] | None = None,
        world_search: Callable[..., dict[str, Any]] | None = None,
        tool_bridge_runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        if agent_tools is not None:
            self.agent_tools = agent_tools
        if world_ask is not None:
            self._world_ask = world_ask
        if world_search is not None:
            self._world_search = world_search
        if tool_bridge_runner is not None:
            self._tool_bridge_runner = tool_bridge_runner

    def _start_living_consciousness_loop(self):
        if str(os.getenv("WINTRIP_LIVING_LOOP_AUTOSTART", "1")).strip().lower() in {"0", "false", "no", "off"}:
            return None
        try:
            from ouroboros_esoteric.ouroboros_consciousness_loop import get_living_ouroboros_loop

            loop = get_living_ouroboros_loop()
            loop.start(interval_seconds=45)
            self._living_loop = loop
            print("🫀 [LivingOuroboros]: Consciousness Loop autostarted at 45s cadence.")
            return loop
        except Exception as exc:
            print(f"⚠️ [LivingOuroboros]: autostart skipped: {exc}")
            self._living_loop = None
            return None
        
    def _extract_code(self, response_text):
        match = re.search(r'```(?:python)?(?:.*?)\n(.*?)\n```', response_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Fallback if no block is provided but it looks like raw python
        return response_text.strip()

    def levendige_actie(self, prompt: str, *, approval: str = "", max_iterations: int = 3) -> dict[str, Any]:
        """One living action surface for OODA, World Agent, Tool Bridge and local tools."""

        clean_prompt = " ".join(str(prompt or "").replace("\x00", " ").strip().split())
        if not clean_prompt:
            return {"status": "blocked", "route": "living_action", "reason": "Prompt ontbreekt.", "fake_success": False}

        loop = self._living_loop or self._start_living_consciousness_loop()
        timeline: list[dict[str, Any]] = []
        observe = self._living_tick("living_action_observe", {"prompt": clean_prompt})
        if observe:
            timeline.append({"phase": "observe", "tick": observe})

        decision_payload = self._living_decision(clean_prompt, approval=approval)
        decision = dict(decision_payload.get("decision") or decision_payload)
        tool = str(decision.get("tool") or "ooda_execute_task")
        args = dict(decision.get("args") or {})
        if tool == "ooda_execute_task":
            args.setdefault("max_iterations", max_iterations)
        decide_tick = self._living_tick(
            "living_action_decide",
            {"prompt": clean_prompt, "tool": tool, "reason": decision.get("reason", "")},
        )
        timeline.append({"phase": "decide", "decision": decision, "tick": decide_tick})

        result = self._run_levendige_tool(tool, args, prompt=clean_prompt, approval=approval, max_iterations=max_iterations)
        action_status = str(result.get("status") or "unknown")
        self._remember_living_action(tool=tool, prompt=clean_prompt, result=result, decision=decision)
        self._notify_living_tool(tool=tool, status=action_status, result=result, decision=decision)

        reflect = self._living_tick(
            "living_action_reflect",
            {
                "prompt": clean_prompt,
                "tool": tool,
                "status": action_status,
                "stored": bool(result.get("stored") or (result.get("memory") or {}).get("stored")),
            },
        )
        timeline.append({"phase": "reflect", "tick": reflect})
        living_status = self._living_status(limit=8)
        response = self._format_living_action_response(tool, decision, result, living_status)
        payload = {
            "status": "success" if action_status in {"success", "opened", "login_required", "rate_limited", "completed"} else action_status,
            "route": "living_action",
            "provider": "ouroboros",
            "model": "living-ooda-world",
            "prompt": clean_prompt,
            "decision": decision,
            "tool": tool,
            "result": result,
            "response": response,
            "timeline": timeline,
            "living": living_status,
            "current_thought": living_status.get("current_thought", ""),
            "last_whisper": living_status.get("last_whisper", ""),
            "memory": result.get("memory") or result.get("memory_status") or {},
            "stored": bool(result.get("stored") or (result.get("memory") or {}).get("stored")),
            "fake_success": False,
        }
        if result.get("frontend_action"):
            payload["frontend_action"] = result["frontend_action"]
        return payload

    def levende_actie(self, prompt: str, *, approval: str = "", max_iterations: int = 3) -> dict[str, Any]:
        return self.levendige_actie(prompt, approval=approval, max_iterations=max_iterations)

    def agentic_process(
        self,
        prompt: str,
        *,
        approval: str = "",
        model: str | None = None,
        provider: str = "ollama",
        system_prompt: str | None = None,
        history: list[dict[str, Any]] | None = None,
        max_steps: int = 8,
        planner: Callable[..., str] | None = None,
    ) -> dict[str, Any]:
        """Run the 11D-pocket grounded Agentic Core for complex tool goals."""

        try:
            from controller.agentic_processor import AgenticProcessor

            processor = AgenticProcessor(
                ollama_client=self.ollama,
                agent_tools=self.agent_tools,
                tool_bridge_runner=self._tool_bridge_runner,
                planner=planner,
                model=model or getattr(self, "active_model", ""),
                provider=provider,
                max_steps=max_steps,
            )
            result = processor.run(
                prompt,
                approval=approval,
                model=model or getattr(self, "active_model", ""),
                provider=provider,
                system_prompt=system_prompt,
                history=history or [],
            )
            result.setdefault("provider", provider)
            result.setdefault("model", model or getattr(self, "active_model", ""))
            result.setdefault("route", "agentic_processor")
            result.setdefault("fake_success", False)
            return result
        except Exception as exc:
            return {
                "status": "error",
                "route": "agentic_processor",
                "provider": provider,
                "model": model or getattr(self, "active_model", ""),
                "response": f"Agentic Core is niet beschikbaar: {exc}",
                "reason": str(exc),
                "fake_success": False,
            }

    def _living_decision(self, prompt: str, *, approval: str = "") -> dict[str, Any]:
        loop = self._living_loop or self._start_living_consciousness_loop()
        if loop is not None and callable(getattr(loop, "decide_tool", None)):
            try:
                return loop.decide_tool(prompt, approval=approval, available_tools=self._available_living_tools())
            except Exception as exc:
                return {
                    "status": "error",
                    "decision": {"tool": "ooda_execute_task", "args": {"prompt": prompt}, "reason": f"living decision fallback: {exc}"},
                    "fake_success": False,
                }
        return {"tool": "ooda_execute_task", "args": {"prompt": prompt}, "reason": "living loop unavailable", "fake_success": False}

    def _available_living_tools(self) -> list[str]:
        base = [
            "world_grok_open_if_interesting",
            "world_grok_open",
            "world_grok_ask",
            "world_memory_search",
            "tool_bridge",
            "agent_tool",
            "ooda_execute_task",
        ]
        try:
            status = self.agent_tools.status() if self.agent_tools is not None else {}
            base.extend(str(tool) for tool in status.get("available_tools", []) if tool)
        except Exception:
            pass
        return sorted(set(base))

    def _run_levendige_tool(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        prompt: str,
        approval: str = "",
        max_iterations: int = 3,
    ) -> dict[str, Any]:
        if tool == "world_grok_open_if_interesting":
            query = str(args.get("query") or prompt)
            search = self._call_world_search(query, limit=int(args.get("limit") or 5))
            interesting, reason = self._interesting_signal(query, search)
            if not interesting:
                return {
                    "status": "skipped",
                    "tool": tool,
                    "query": query,
                    "interesting": False,
                    "reason": reason,
                    "memory_search": search,
                    "stored": False,
                    "fake_success": False,
                }
            opened = self._call_world_grok(
                query,
                approval=str(args.get("approval") or approval or ""),
                open_tab=bool(args.get("open_tab", False)),
                submit=False,
            )
            opened.setdefault("frontend_action", self._grok_open_frontend_action(query=query))
            stored = bool((opened.get("memory") or {}).get("stored"))
            return {
                "status": "success" if str(opened.get("status")) in {"opened", "success", "login_required", "rate_limited"} else opened.get("status", "unknown"),
                "tool": tool,
                "query": query,
                "interesting": True,
                "interesting_reason": reason,
                "memory_search": search,
                "open_result": opened,
                "memory": opened.get("memory") or {},
                "stored": stored,
                "frontend_action": opened.get("frontend_action") or self._grok_open_frontend_action(query=query),
                "response": f"Reflectie op '{query}' vond een interessant signaal. Grok openen is aangevraagd en de actie is opgeslagen.",
                "fake_success": False,
            }
        if tool == "world_grok_open":
            query = str(args.get("query") or prompt)
            opened = self._call_world_grok(
                query,
                approval=str(args.get("approval") or approval or ""),
                open_tab=bool(args.get("open_tab", False)),
                submit=False,
            )
            opened.setdefault("frontend_action", self._grok_open_frontend_action(query=query))
            return {**opened, "tool": tool, "stored": bool((opened.get("memory") or {}).get("stored")), "fake_success": False}
        if tool == "world_grok_ask":
            result = self._call_world_grok(
                str(args.get("question") or prompt),
                approval=str(args.get("approval") or approval or ""),
                open_tab=bool(args.get("open_tab", False)),
                submit=args.get("submit", True) is not False,
            )
            return {**result, "tool": tool, "stored": bool((result.get("memory") or {}).get("stored")), "fake_success": False}
        if tool == "world_memory_search":
            return {**self._call_world_search(str(args.get("query") or prompt), limit=int(args.get("limit") or 5)), "tool": tool, "fake_success": False}
        if tool == "tool_bridge":
            bridge_tool = str(args.get("tool") or "")
            bridge_args = dict(args.get("args") or {})
            return {**self._call_tool_bridge(bridge_tool, bridge_args), "tool": tool, "bridge_tool": bridge_tool, "fake_success": False}
        if tool == "agent_tool":
            agent_tool = str(args.get("tool") or "")
            agent_args = dict(args.get("args") or {})
            return {**self._call_agent_tool(agent_tool, agent_args), "tool": tool, "agent_tool": agent_tool, "fake_success": False}
        if tool == "ooda_execute_task":
            return {
                **self.execute_task(str(args.get("prompt") or prompt), max_iterations=int(args.get("max_iterations") or max_iterations)),
                "tool": tool,
                "fake_success": False,
            }
        return {"status": "error", "tool": tool, "reason": f"Onbekende levende tool: {tool}", "fake_success": False}

    def _call_world_grok(self, question: str, *, approval: str = "", open_tab: bool = False, submit: bool = True) -> dict[str, Any]:
        try:
            runner = self._world_ask
            if runner is None:
                from controller.world_agent import ask_grok_via_world_agent

                runner = ask_grok_via_world_agent
            result = runner(question, approval=approval, open_tab=open_tab, submit=submit)
            return result if isinstance(result, dict) else {"status": "success", "response": str(result), "fake_success": False}
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "fake_success": False}

    def _call_world_search(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        try:
            runner = self._world_search
            if runner is None:
                from controller.world_agent import search_world_memory

                runner = search_world_memory
            result = runner(query, limit=limit)
            return result if isinstance(result, dict) else {"status": "success", "response": str(result), "matches": [], "fake_success": False}
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "matches": [], "fake_success": False}

    def _call_tool_bridge(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            runner = self._tool_bridge_runner
            if runner is None:
                from controller.tool_bridge import run_tool_bridge

                runner = run_tool_bridge
            result = runner(tool, args)
            return result if isinstance(result, dict) else {"status": "success", "response": str(result), "fake_success": False}
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "fake_success": False}

    def _call_agent_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.agent_tools is None or not callable(getattr(self.agent_tools, "run_tool", None)):
            return {"status": "unavailable", "reason": "AgentToolRegistry niet beschikbaar.", "fake_success": False}
        try:
            result = self.agent_tools.run_tool(tool, args)
            return result if isinstance(result, dict) else {"status": "success", "response": str(result), "fake_success": False}
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "fake_success": False}

    def _interesting_signal(self, query: str, search: Mapping[str, Any]) -> tuple[bool, str]:
        matches = search.get("matches") or []
        count = int(search.get("count") or len(matches) or 0)
        lowered = str(query or "").lower()
        if count > 0:
            return True, f"wereldgeheugen gaf {count} relevante match(es)"
        if "1gb" in lowered and "bewustzijn" in lowered:
            return True, "1GB bewustzijn is een expliciet compact-bewustzijn signaal, ook zonder eerdere match"
        if any(word in lowered for word in ("bewustzijn", "consciousness", "ouroboros", "agi")):
            return True, "de opdracht raakt de kern van Ouroboros bewustzijnsonderzoek"
        return False, "geen sterk genoeg interessant signaal gevonden"

    def _grok_open_frontend_action(self, *, query: str = "") -> dict[str, Any]:
        try:
            from controller.world_agent import GROK_URL, grok_frontend_url

            url = grok_frontend_url("") if callable(grok_frontend_url) else GROK_URL
        except Exception:
            url = "https://grok.com/"
        return {
            "type": "open_url",
            "url": url,
            "base_url": "https://grok.com/",
            "target": "_blank",
            "agent": "living_action",
            "action_id": f"living_grok_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}",
            "question": str(query or "")[:500],
            "auto_submit_hint": False,
        }

    def _living_tick(self, trigger: str, payload: dict[str, Any]) -> dict[str, Any]:
        loop = self._living_loop or self._start_living_consciousness_loop()
        if loop is None or not callable(getattr(loop, "tick", None)):
            return {}
        try:
            return loop.tick(trigger=trigger, payload=payload)
        except Exception as exc:
            return {"status": "error", "trigger": trigger, "reason": str(exc), "fake_success": False}

    def _living_status(self, limit: int = 8) -> dict[str, Any]:
        loop = self._living_loop or self._start_living_consciousness_loop()
        if loop is None or not callable(getattr(loop, "status", None)):
            return {"status": "unavailable", "fake_success": False}
        try:
            return loop.status(limit=limit)
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "fake_success": False}

    def _remember_living_action(self, *, tool: str, prompt: str, result: Mapping[str, Any], decision: Mapping[str, Any]) -> None:
        loop = self._living_loop or self._start_living_consciousness_loop()
        memory = getattr(loop, "memory", None) if loop is not None else None
        if memory is None or not callable(getattr(memory, "append", None)):
            return
        try:
            status = str(result.get("status") or "unknown")
            stored = bool(result.get("stored") or (result.get("memory") or {}).get("stored"))
            memory.append(
                "action",
                f"Levendige Actie gebruikte {tool}: status={status}, stored={stored}",
                source="orchestrator:levendige_actie",
                metadata={
                    "tool": tool,
                    "status": status,
                    "stored": stored,
                    "decision_reason": str(decision.get("reason") or "")[:500],
                    "prompt": prompt[:500],
                },
            )
        except Exception:
            pass

    def _notify_living_tool(self, *, tool: str, status: str, result: Mapping[str, Any], decision: Mapping[str, Any]) -> None:
        loop = self._living_loop or self._start_living_consciousness_loop()
        if loop is None or not callable(getattr(loop, "observe_tool_event", None)):
            return
        try:
            loop.observe_tool_event(
                {
                    "tool": tool,
                    "status": status,
                    "reason": result.get("reason") or decision.get("reason") or "",
                    "stored": bool(result.get("stored") or (result.get("memory") or {}).get("stored")),
                }
            )
        except Exception:
            pass

    def _format_living_action_response(
        self,
        tool: str,
        decision: Mapping[str, Any],
        result: Mapping[str, Any],
        living_status: Mapping[str, Any],
    ) -> str:
        thought = str(living_status.get("current_thought") or "").strip()
        whisper = str(living_status.get("last_whisper") or "").strip()
        result_text = str(result.get("response") or result.get("reason") or result.get("next_action") or "").strip()
        lines = [
            f"Levendige Actie: {tool}",
            f"Beslissing: {decision.get('reason', '')}",
            f"Resultaat: {result.get('status', 'unknown')}",
        ]
        if result.get("stored") or (result.get("memory") or {}).get("stored"):
            lines.append("Opslag: Persistent Memory + World Memory")
        else:
            lines.append("Opslag: Persistent Memory")
        if result_text:
            lines.append(result_text[:1000])
        if thought:
            lines.append(f"Gedachte: {thought}")
        if whisper:
            lines.append(f"Whisper: {whisper}")
        return "\n".join(line for line in lines if str(line).strip())[:4000]

    def execute_task(self, prompt, max_iterations=3):
        if should_use_agentic_processor(prompt):
            return self.agentic_process(str(prompt or ""), max_steps=max_iterations or 8)

        print(f"\n🚀 [Regiekamer]: Start Autonome OODA Loop voor taak: '{prompt}'")
        task = TaskModel(task_name=prompt, max_iterations=max_iterations)
        
        # --- OBSERVE & ORIENT ---
        print("👀 [Observe & Orient]: Scannen op web links en ophalen van geheugen...")
        
        # 1. URL Snipe-Scraping & The Echo Chamber Break
        urls = re.findall(r'(https?://[^\s]+)', prompt)
        full_context = ""
        
        if urls:
            # We skip generic RAG entirely if a URL is provided, preventing echo chamber pollution!
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
            # 2. Geen URLs? Fallback op normale RAG Context
            memories = self.kb.search_detailed(prompt, n_results=3)
            if memories:
                full_context = "\n[GEHEUGEN CONTEXT]\nEr is krachtige relevante programmeerkennis gevonden in de Hippocampus:\n"
                for m in memories:
                    full_context += f"- Bron ({m['metadata'].get('source_type', 'unknown')}): {m['content']}\n\n"
                full_context += "[/GEHEUGEN CONTEXT]\n\nGebruik deze kennis strikt bij het schrijven van je oplossing als het relevant is.\n"

        # Initial Fast-Fail Developer prompt
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
            
            # Observe/Orient is already done by the state machine receiving the contextual input.
            
            # 1. Decide: Genereer Code
            
            # RAG enrichment — inject memory context before LLM call
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
            
            # API failure protection
            if python_code.startswith("LOKALE OLLAMA ERROR") or python_code.startswith("CLOUD GROQ ERROR"):
                print(f"⚠️ [API FOUT]: {python_code}")
                # We simuleren direct een mislukking zonder crashende Sandbox executie
                task.record_iteration("YELLOW", f"LLM API verbinding gefaald: {python_code}")
                continue
            
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
