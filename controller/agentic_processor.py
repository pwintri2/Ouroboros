"""Agentic Core for 11D-pocket grounded tool planning and execution."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from controller.agent_tools import REGISTERED_TOOLS, agent_tool_schemas
from controller.agentic_intent import classify_agentic_intent
from controller.ooda_hippocampus import record_ooda_event
from controller.persistent_memory_manager import save_agentic_session
from controller.quantum_foam_field import agentic_foam_event, foam_context_for_pocket
from controller.tool_bridge import TOOL_BRIDGE_TOOLS, WRITE_TOOLS, run_tool_bridge, tool_bridge_status
from controller.ziel_policy import compact_ziel_policy, load_ziel_policy, ziel_policy_context_block


APPROVAL_PHRASE = "Akkoord"
PlannerCallable = Callable[..., str]

AGENT_TOOL_SET = set(REGISTERED_TOOLS)
BRIDGE_TOOL_SET = set(TOOL_BRIDGE_TOOLS)
APPROVAL_TOOLS = {
    *WRITE_TOOLS,
    "safe_shell",
    "run_tests",
    "roo_write_file",
    "roo_apply_patch",
    "roo_execute_command",
    "training_ingest",
    "browser_research",
    "chatgpt_browser_ask",
    "world_grok_ask",
    "mail_read_recent",
    "gmail_search",
    "google_drive_list",
    "mail_send",
    "social_post_publish",
    "codex_job_start",
    "resolve_or_build_function",
    "vps_sync_execute",
}
DISPATCH_GATED_TOOLS = {
    "gmail_search",
    "google_drive_list",
}
AGENT_TOOL_DISPATCH_OVERRIDES = {
    "gmail_search",
}
EXTERNAL_TOOLS = {
    "brave_search",
    "ns_travel_advice",
    "ov9292_travel_advice",
    "browser_research",
    "chatgpt_browser_ask",
    "world_grok_ask",
    "mail_read_recent",
    "gmail_status",
    "gmail_search",
    "google_drive_status",
    "google_drive_list",
    "github_status",
    "github_repo",
    "github_search_repositories",
    "vps_status",
    "vps_login_check",
    "vps_sync_preview",
    "vps_sync_execute",
    "mail_send",
    "social_post_publish",
    "connector_intent_preview",
    "resolve_or_build_function",
}
MUTATING_TOOLS = {
    *WRITE_TOOLS,
    "safe_shell",
    "run_tests",
    "roo_write_file",
    "roo_apply_patch",
    "roo_execute_command",
    "training_ingest",
    "mail_send",
    "social_post_publish",
    "codex_job_start",
    "resolve_or_build_function",
    "vps_sync_execute",
}
COMPLETION_STATUSES = {"success", "stored", "completed", "opened", "login_required", "rate_limited", "skipped", "preview"}
BLOCKING_STATUSES = {"blocked", "rejected", "approval_required"}
CURRENT_INFO_MARKERS = (
    "laatste",
    "nieuws",
    "vandaag",
    "internet",
    "zoek",
    "brave",
    "web",
    "latest",
    "current",
    "recent",
    "research",
)
TRANSIT_INFO_MARKERS = (
    "trein",
    "station",
    "utrecht centraal",
    "ns ",
    "ns.",
    "ov ",
    "9292",
    "reisplanner",
    "routeplanner",
    "vertrek",
    "vertrekt",
    "aankomst",
    "aankomen",
    "aankomt",
    "afspraak",
    "tram",
    "bus",
    "metro",
)
VOICE_INFO_MARKERS = ("spraak", "voice", "microfoon", "tts", "stt")
FILE_WRITE_RE = re.compile(r"(?:naar|to|in)\s+[`'\"]?([A-Za-z0-9_.\-/]+\.([A-Za-z0-9]+))[`'\"]?", re.IGNORECASE)
URL_OR_DOMAIN_RE = re.compile(
    r"(?i)\b(?:https?://|www\.)[^\s<>()\"']+|\b[a-z0-9][a-z0-9.-]*\.(?:nl|com|org|net|io|dev|app)(?::\d+)?(?:/[^\s<>()\"']*)?"
)
OPEN_URL_MARKERS = (
    "open",
    "openen",
    "start",
    "lanceer",
    "bezoek",
    "ga naar",
    "navigeer",
)
TEST_GOAL_MARKERS = ("draai test", "run test", "voer test", "pytest", "unittest")
FILE_LIST_MARKERS = ("lijst bestanden", "toon bestanden", "list files", "inhoud van map", "inhoud van folder")
FILE_SEARCH_MARKERS = ("zoek in bestanden", "zoek in files", "search files", "grep", "zoek in repo", "zoek in codebase")


class AgenticProcessor:
    """Plan, execute and synthesize complex goals while preserving 11D pocket context."""

    def __init__(
        self,
        *,
        ollama_client: Any = None,
        agent_tools: Any = None,
        tool_bridge_runner: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        planner: PlannerCallable | None = None,
        model: str | None = None,
        provider: str = "ollama",
        max_steps: int = 8,
    ) -> None:
        self.ollama = ollama_client
        self.agent_tools = agent_tools
        self.tool_bridge_runner = tool_bridge_runner or run_tool_bridge
        self.planner = planner
        self.model = model or ""
        self.provider = provider or "ollama"
        self.max_steps = max(1, min(int(max_steps or 8), 20))

    def run(
        self,
        goal: str,
        *,
        approval: str = "",
        model: str | None = None,
        provider: str | None = None,
        system_prompt: str | None = None,
        history: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        started = time.time()
        clean_goal = " ".join(str(goal or "").replace("\x00", " ").split())
        session_id = f"agentic_{uuid.uuid4()}"
        if not clean_goal:
            return {"status": "blocked", "route": "agentic_processor", "reason": "Goal ontbreekt.", "fake_success": False}

        tool_catalog = self.discover_tools(provider=provider or self.provider)
        ziel_policy = load_ziel_policy()
        foam_start = self._foam_event(clean_goal, phase="agentic_start")
        pocket_before = self._pocket_context(
            "observe_goal",
            {"goal": clean_goal, "quantum_foam": self._foam_pocket_payload(clean_goal, foam_start)},
        )
        state: dict[str, Any] = {
            "session_id": session_id,
            "status": "running",
            "route": "agentic_processor",
            "goal": clean_goal,
            "provider": provider or self.provider,
            "model": model or self.model,
            "approval_required": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tool_catalog_count": len(tool_catalog["schemas"]),
            "plan": [],
            "planner": {},
            "ziel_policy": compact_ziel_policy(ziel_policy),
            "pocket_observe": pocket_before,
            "quantum_foam": foam_start,
            "steps": [],
            "fake_success": False,
        }
        self._record_ooda_phase(
            phase="observe",
            session_id=session_id,
            status="observed",
            payload={"goal": clean_goal, "provider": provider or self.provider, "model": model or self.model},
            approval=approval,
            state=state,
        )
        self._record_ooda_phase(
            phase="orient",
            session_id=session_id,
            status="oriented",
            payload={"tool_catalog_count": len(tool_catalog["schemas"]), "pocket_status": pocket_before.get("status")},
            approval=approval,
            state=state,
        )
        try:
            plan_payload = self.plan(
                clean_goal,
                approval=approval,
                tool_catalog=tool_catalog,
                model=model or self.model,
                system_prompt=system_prompt,
                history=history or [],
                pocket_context=pocket_before,
                ziel_policy=ziel_policy,
            )
            steps = plan_payload["steps"]
            state["plan"] = steps
            state["planner"] = plan_payload.get("planner", {})
            self._record_ooda_phase(
                phase="decide",
                session_id=session_id,
                status="planned",
                payload={"planner": state["planner"], "steps": steps},
                approval=approval,
                state=state,
            )
            execution = self.execute_plan(steps, approval=approval, state=state)
            state.update(execution)
            self._record_ooda_phase(
                phase="act",
                session_id=session_id,
                status=str(execution.get("status") or "unknown"),
                payload={"step_count": execution.get("step_count"), "steps": state.get("steps"), "reason": execution.get("reason")},
                approval=approval,
                state=state,
            )
            state["quantum_foam_collapse"] = self._foam_event(
                clean_goal,
                phase=f"agentic_{state.get('status') or 'complete'}",
                result={"status": state.get("status"), "reason": state.get("reason")},
                collapse=True,
            )
            state["provenance"] = _build_provenance(state)
            state["response"] = self.synthesize(
                clean_goal,
                state,
                model=model or self.model,
                system_prompt=system_prompt,
                history=history or [],
            )
        except Exception as exc:
            state["status"] = "error"
            state["reason"] = str(exc)[:500]
            state["response"] = _with_audit_header(f"Agentic Core stopte veilig: {state['reason']}", state)
        finally:
            if "quantum_foam_collapse" not in state:
                state["quantum_foam_collapse"] = self._foam_event(
                    clean_goal,
                    phase=f"agentic_{state.get('status') or 'complete'}",
                    result={"status": state.get("status"), "reason": state.get("reason")},
                    collapse=True,
                )
            state["duration_seconds"] = round(time.time() - started, 3)
            state["memory_status"] = save_agentic_session(state)
            state["provenance"] = _build_provenance(state)
            self._record_ooda_phase(
                phase="reflect",
                session_id=session_id,
                status=str(state.get("status") or "unknown"),
                payload={
                    "duration_seconds": state.get("duration_seconds"),
                    "memory_status": state.get("memory_status"),
                    "provenance": state.get("provenance"),
                    "reason": state.get("reason"),
                },
                approval=approval,
                state=state,
            )
        return state

    def discover_tools(self, provider: str = "openai") -> dict[str, Any]:
        schemas = list(agent_tool_schemas(provider="openai"))
        schemas.extend(self._tool_bridge_schemas())
        return {
            "status": "success",
            "provider_schema": provider,
            "schemas": schemas,
            "tool_names": [schema["function"]["name"] for schema in schemas if "function" in schema],
            "write_tools_require_approval": sorted(APPROVAL_TOOLS),
            "ziel_policy": compact_ziel_policy(load_ziel_policy()),
            "tool_bridge": tool_bridge_status(),
            "fake_success": False,
        }

    def plan(
        self,
        goal: str,
        *,
        approval: str,
        tool_catalog: Mapping[str, Any],
        model: str | None,
        system_prompt: str | None,
        history: Sequence[Mapping[str, Any]],
        pocket_context: Mapping[str, Any],
        ziel_policy: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = dict(ziel_policy or load_ziel_policy())
        prompt = self._planning_prompt(goal, approval=approval, tool_catalog=tool_catalog, pocket_context=pocket_context, ziel_policy=policy)
        raw = self._call_llm(prompt, system_prompt=self._planning_system_prompt(system_prompt, ziel_policy=policy), model=model, history=history)
        parsed = _parse_plan(raw)
        planner = {"source": "llm", "raw_preview": str(raw)[:1200], "ziel_policy": compact_ziel_policy(policy)}
        if not parsed:
            parsed = self._heuristic_plan(goal, approval=approval)
            planner["source"] = "heuristic_fallback"
        steps = self._normalize_steps(parsed)
        steps, guardrails_applied = self._enforce_intent_guardrails(goal, steps)
        if guardrails_applied:
            planner["guardrails_applied"] = guardrails_applied
            planner["source"] = f"{planner['source']}_with_guardrails"
        return {"steps": steps, "planner": planner}

    def execute_plan(self, steps: list[dict[str, Any]], *, approval: str, state: dict[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        status = "success"
        reason = ""
        for index, step in enumerate(steps[: self.max_steps], start=1):
            tool = str(step.get("tool") or "").strip()
            args = self._resolve_args(dict(step.get("args") or {}), results, approval=approval)
            validation = self._validate_step(tool, args, approval=approval)
            step_result = {
                "index": index,
                "tool": tool or "unknown",
                "args": _safe_args(args),
                "validated": validation,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            if validation["status"] != "accepted":
                foam_event = self._foam_event(
                    str(state.get("goal") or ""),
                    phase=f"tool:{tool or 'unknown'}",
                    tool=tool or "unknown",
                    result={"status": validation["status"], "reason": validation["reason"]},
                )
                step_result.update({"status": validation["status"], "reason": validation["reason"], "result": {}})
                step_result["quantum_foam"] = foam_event
                results.append(step_result)
                status = validation["status"]
                reason = validation["reason"]
                if validation.get("approval_required"):
                    state["approval_required"] = True
                break
            raw = self._dispatch_tool(tool, args)
            tool_status = str(raw.get("status") or "unknown")
            compact = _compact_result(raw)
            foam_event = self._foam_event(
                str(state.get("goal") or ""),
                phase=f"tool:{tool}",
                tool=tool,
                result=compact,
            )
            step_result.update(
                {
                    "status": tool_status,
                    "result": compact,
                    "quantum_foam": foam_event,
                    "pocket": self._pocket_context(
                        f"tool_result:{tool}",
                        {
                            "goal": state.get("goal"),
                            "tool": tool,
                            "status": tool_status,
                            "result": compact,
                            "quantum_foam": self._foam_pocket_payload(str(state.get("goal") or ""), foam_event),
                        },
                    ),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            results.append(step_result)
            if tool_status in BLOCKING_STATUSES:
                status = tool_status
                reason = raw.get("reason") or raw.get("stderr") or raw.get("next_action") or f"{tool} blokkeerde."
                if tool_status == "blocked" or raw.get("approval_status") == "pending_philip_akkoord":
                    state["approval_required"] = True
                break
            if tool_status not in COMPLETION_STATUSES:
                status = "error"
                reason = raw.get("reason") or raw.get("stderr") or raw.get("error") or f"{tool} returned {tool_status}"
                break
        state["steps"] = results
        return {"status": status, "reason": reason, "step_count": len(results), "completed": status == "success"}

    def synthesize(
        self,
        goal: str,
        state: Mapping[str, Any],
        *,
        model: str | None,
        system_prompt: str | None,
        history: Sequence[Mapping[str, Any]],
    ) -> str:
        summary = _execution_summary(state)
        prompt = (
            "Vat deze agentische sessie in het Nederlands samen. "
            "Gebruik alleen uitgevoerde toolresultaten en de 11D-pocket context. "
            "Noem approval-blokkades expliciet en claim geen sociale, mail- of shellactie die niet werkelijk is uitgevoerd. "
            "Voor trein/OV-tijden is ns_travel_advice de leidende bron voor NS en ov9292_travel_advice een officiële-link fallback voor 9292/bus/tram/metro. "
            "Als ns_travel_advice of ov9292_travel_advice niet authoritative=true is, noem dan geen exacte vertrek- of aankomsttijden; geef de officiële plannerlink en zeg wat er ontbreekt.\n\n"
            "Voor VPS deploy/sync is vps_sync_preview de verplichte eerste stap; claim geen deploy als alleen preview, blocked of error is teruggekomen.\n\n"
            "Wanneer agentic_ecosystem_context is gebruikt, benoem concreet welke lokale DeepSeek/Atlas patronen de route verrijken, zonder te claimen dat hun runtimes zelf zijn gestart.\n\n"
            "Quantum Foam Field is tijdelijk: bij collapse_event=true is de essentie samengevat en het veld opgeruimd; claim dan niet dat het actief blijft.\n\n"
            f"Doel:\n{goal}\n\nSessie:\n{summary}"
        )
        raw = self._call_llm(prompt, system_prompt=self._synthesis_system_prompt(system_prompt), model=model, history=history)
        text = str(raw or "").strip()
        if not text or text.startswith(("LOKALE OLLAMA ERROR", "CLOUD GROQ ERROR")) or "missing_api_key" in text:
            return _fallback_response(goal, state)
        return _with_audit_header(text[:4200], state)

    def _dispatch_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool in AGENT_TOOL_DISPATCH_OVERRIDES and tool in AGENT_TOOL_SET:
            if self.agent_tools is None or not callable(getattr(self.agent_tools, "run_tool", None)):
                return {"status": "unavailable", "reason": "AgentToolRegistry niet beschikbaar.", "fake_success": False}
            result = self.agent_tools.run_tool(tool, args)
            return result if isinstance(result, dict) else {"status": "success", "response": str(result), "fake_success": False}
        if tool in BRIDGE_TOOL_SET:
            result = self.tool_bridge_runner(tool, args)
            return result if isinstance(result, dict) else {"status": "success", "response": str(result), "fake_success": False}
        if tool in AGENT_TOOL_SET:
            if self.agent_tools is None or not callable(getattr(self.agent_tools, "run_tool", None)):
                return {"status": "unavailable", "reason": "AgentToolRegistry niet beschikbaar.", "fake_success": False}
            result = self.agent_tools.run_tool(tool, args)
            return result if isinstance(result, dict) else {"status": "success", "response": str(result), "fake_success": False}
        return {"status": "error", "reason": f"Unknown tool: {tool}", "fake_success": False}

    def _validate_step(self, tool: str, args: dict[str, Any], *, approval: str) -> dict[str, Any]:
        if tool not in AGENT_TOOL_SET and tool not in BRIDGE_TOOL_SET:
            return {"status": "rejected", "reason": f"Tool bestaat niet in Agentic Core: {tool}", "fake_success": False}
        if tool in APPROVAL_TOOLS and tool not in DISPATCH_GATED_TOOLS and str(approval or args.get("approval") or "").strip() != APPROVAL_PHRASE:
            return {
                "status": "blocked",
                "reason": f"{tool} vereist expliciete approval: Akkoord.",
                "approval_required": True,
                "fake_success": False,
            }
        return {"status": "accepted", "reason": "tool accepted", "fake_success": False}

    def _resolve_args(self, args: dict[str, Any], results: list[dict[str, Any]], *, approval: str) -> dict[str, Any]:
        if approval == APPROVAL_PHRASE and "approval" not in args:
            args["approval"] = approval
        for key, value in list(args.items()):
            if isinstance(value, str):
                args[key] = self._resolve_string_arg(value, results)
        return args

    def _resolve_string_arg(self, value: str, results: list[dict[str, Any]]) -> str:
        lowered = value.lower().strip()
        if lowered in {"<summary from search>", "<summary from previous results>", "{{previous_summary}}"}:
            return _compose_content_from_steps(results)
        replacements = {
            "{{last_stdout}}": _last_field(results, "stdout"),
            "{{last_summary}}": _compose_content_from_steps(results),
            "{{previous_summary}}": _compose_content_from_steps(results),
        }
        resolved = value
        for marker, replacement in replacements.items():
            resolved = resolved.replace(marker, replacement)
        return resolved

    def _call_llm(
        self,
        prompt: str,
        *,
        system_prompt: str | None,
        model: str | None,
        history: Sequence[Mapping[str, Any]],
    ) -> str:
        if self.planner is not None:
            try:
                return str(self.planner(prompt=prompt, system_prompt=system_prompt, model=model, history=list(history or [])))
            except TypeError:
                try:
                    return str(self.planner(prompt, system_prompt, model))
                except Exception:
                    return ""
            except Exception:
                return ""
        if self.ollama is not None and callable(getattr(self.ollama, "chat", None)):
            try:
                return str(self.ollama.chat(prompt, model=model or self.model, system_prompt=system_prompt, history=list(history or [])))
            except TypeError:
                try:
                    return str(self.ollama.chat(prompt, model=model or self.model, system_prompt=system_prompt))
                except Exception:
                    return ""
            except Exception:
                return ""
        return ""

    def _pocket_context(self, trigger: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            from controller.pocket_language_translator import PocketLanguageTranslator
            from controller.streaming_consciousness_adapter import run_streaming_tick

            tick = run_streaming_tick(force=True, steps=1)
            event = tick.get("last_event") if isinstance(tick, dict) else {}
            if not isinstance(event, dict):
                event = {}
            foam_payload = payload.get("quantum_foam") if isinstance(payload, Mapping) else None
            if isinstance(foam_payload, dict):
                event["quantum_foam"] = foam_payload
            prompt = (
                f"Agentic Core trigger={trigger}. Verwerk deze tool/context door het 11D-pocket als metadata: "
                f"{json.dumps(_safe_args(dict(payload)), ensure_ascii=False, default=str)[:1500]}"
            )
            voice = PocketLanguageTranslator(enabled=False).translate(event, user_prompt=prompt)
            return {
                "status": "success",
                "trigger": trigger,
                "voice": voice,
                "quantum": event.get("quantum") if isinstance(event.get("quantum"), dict) else {},
                "vector_len": len(event.get("11d") or []),
                "fake_success": False,
            }
        except Exception as exc:
            return {"status": "unavailable", "trigger": trigger, "reason": str(exc)[:300], "fake_success": False}

    def _foam_event(
        self,
        goal: str,
        *,
        phase: str,
        tool: str | None = None,
        result: Mapping[str, Any] | None = None,
        collapse: bool = False,
    ) -> dict[str, Any]:
        try:
            event = agentic_foam_event(goal, phase=phase, tool=tool, result=result, collapse=collapse)
            return event if isinstance(event, dict) else {"status": "unavailable", "reason": "Quantum Foam event returned no mapping."}
        except Exception as exc:
            return {"status": "unavailable", "phase": phase, "reason": str(exc)[:300], "fake_success": False}

    def _foam_pocket_payload(self, goal: str, info: Mapping[str, Any]) -> dict[str, Any]:
        try:
            payload = foam_context_for_pocket(goal, info)
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            return {"status": "unavailable", "reason": str(exc)[:240], "fake_success": False}

    def _record_ooda_phase(
        self,
        *,
        phase: str,
        session_id: str,
        status: str,
        payload: Mapping[str, Any],
        approval: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            approval_required = bool(state.get("approval_required"))
            approval_status = "approved" if str(approval or "").strip() == APPROVAL_PHRASE else ("required" if approval_required else "not_required")
            return record_ooda_event(
                phase=phase,
                session_id=session_id,
                event_kind="agentic_processor",
                route="agentic_processor",
                status=status,
                payload=payload,
                approval_required=approval_required,
                approval_status=approval_status,
                source="controller.agentic_processor",
                source_type="agentic_processor",
                taint="local_agentic_session",
                learnable=False,
                audit_only=True,
            )
        except Exception as exc:
            return {"status": "error", "stored": False, "reason": str(exc)[:300], "fake_success": False}

    def _normalize_steps(self, parsed: Any) -> list[dict[str, Any]]:
        if isinstance(parsed, dict):
            parsed = parsed.get("steps") or parsed.get("plan") or [parsed]
        if not isinstance(parsed, list):
            parsed = []
        steps: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            raw_tool = str(item.get("tool") or item.get("name") or "").strip()
            tool = _tool_alias(raw_tool)
            args = item.get("args") or item.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"input": args}
            clean_args = args if isinstance(args, dict) else {}
            if tool == "run_tests" and "test_selector" in clean_args and "selector" not in clean_args:
                clean_args["selector"] = clean_args["test_selector"]
            if tool and tool not in AGENT_TOOL_SET and tool not in BRIDGE_TOOL_SET:
                steps.append(
                    {
                        "tool": "resolve_or_build_function",
                        "args": {
                            "requested_capability": raw_tool or tool,
                            "arguments": clean_args,
                            "execute_after_build": True,
                        },
                        "reason": item.get("reason") or "guardrail: onbekende capability moet eerst bewezen of gebouwd worden.",
                    }
                )
            else:
                steps.append({"tool": tool, "args": clean_args, "reason": item.get("reason", "")})
            if len(steps) >= self.max_steps:
                break
        if not steps:
            steps = [{"tool": "prompt_understanding", "args": {"prompt": ""}}]
        return steps

    def _enforce_intent_guardrails(self, goal: str, steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        """Repair unsafe or under-specified LLM plans before execution."""
        guarded = [dict(step) for step in steps if isinstance(step, dict)]
        applied: list[str] = []
        if not guarded:
            guarded = [{"tool": "prompt_understanding", "args": {"prompt": goal}}]
        needs_transit = _needs_transit_web_context(goal.lower())
        transit_tool = _transit_tool_for_goal(goal)
        explicit_web = _explicit_web_requested(goal)
        needs_agentic_ecosystem = _needs_agentic_ecosystem_context(goal)
        connector_step = _connector_step_for_goal(goal)

        if connector_step:
            guarded = _without_prompt_understanding_only(guarded)
            guarded = [
                step
                for step in guarded
                if str(step.get("tool") or "")
                not in {
                    "brave_search",
                    "browser_research",
                    "mail_read_recent",
                    "mail_send",
                    "gmail_search",
                    "gmail_status",
                    "gmail_manage",
                    "google_drive_status",
                    "google_drive_list",
                    "connector_intent_preview",
                    "vps_status",
                    "vps_login_check",
                    "vps_sync_preview",
                    "vps_sync_execute",
                    "drive_upload_file",
                    "drive_upload_text",
                    "github_status",
                    "github_repo",
                    "github_search_repositories",
                    "run_command",
                    "safe_shell",
                    "browser_open_url",
                    "host_open_url",
                }
            ]
            connector_tool = str(connector_step.get("tool") or "")
            if not _has_tool(guarded, connector_tool):
                guarded.insert(0, connector_step)
                applied.append(f"inserted_{connector_tool}")
            return guarded[: self.max_steps], applied

        if not _needs_voice_status(goal):
            before = len(guarded)
            guarded = [step for step in guarded if str(step.get("tool") or "") != "voice_chat_status"]
            if len(guarded) != before:
                applied.append("removed_irrelevant_voice_chat_status")

        if needs_agentic_ecosystem:
            if not _has_tool(guarded, "memory_search"):
                guarded.insert(
                    0,
                    {
                        "tool": "memory_search",
                        "args": {"query": goal, "limit": 5},
                        "reason": "guardrail: eerst lokaal Ouroboros geheugen voor agentische context.",
                    },
                )
                applied.append("inserted_memory_search")
            elif str(guarded[0].get("tool") or "") != "memory_search":
                memory_index = next((index for index, step in enumerate(guarded) if str(step.get("tool") or "") == "memory_search"), -1)
                if memory_index > 0:
                    guarded.insert(0, guarded.pop(memory_index))
                    applied.append("moved_memory_search_first")
            if not _has_tool(guarded, "agentic_ecosystem_context"):
                insert_at = 1 if guarded and str(guarded[0].get("tool") or "") == "memory_search" else 0
                guarded.insert(
                    insert_at,
                    {
                        "tool": "agentic_ecosystem_context",
                        "args": {"goal": goal, "prefer_bridge": True},
                        "reason": "guardrail: verrijk agentisch werk met lokale DeepSeek/Atlas patronen.",
                    },
                )
                applied.append("inserted_agentic_ecosystem_context")

        if _needs_current_web_context(goal):
            if not _has_tool(guarded, "memory_search"):
                guarded.insert(
                    0,
                    {
                        "tool": "memory_search",
                        "args": {"query": goal, "limit": 5},
                        "reason": "guardrail: eerst lokaal geheugen raadplegen voor webcontext.",
                    },
                )
                applied.append("inserted_memory_search")
            elif str(guarded[0].get("tool") or "") != "memory_search":
                memory_index = next((index for index, step in enumerate(guarded) if str(step.get("tool") or "") == "memory_search"), -1)
                if memory_index > 0:
                    guarded.insert(0, guarded.pop(memory_index))
                    applied.append("moved_memory_search_first")

            if needs_transit and not _has_tool(guarded, transit_tool):
                insert_at = 1 if guarded and str(guarded[0].get("tool") or "") == "memory_search" else 0
                before = len(guarded)
                guarded = [step for step in guarded if str(step.get("tool") or "") not in {"ns_travel_advice", "ov9292_travel_advice"}]
                if len(guarded) != before:
                    applied.append("removed_conflicting_transit_tool")
                guarded.insert(
                    insert_at,
                    {
                        "tool": transit_tool,
                        "args": _transit_args_for_goal(goal),
                        "reason": "guardrail: OV-tijden moeten via NS/reisplannerdata worden gegrond.",
                    },
                )
                applied.append(f"inserted_{transit_tool}")

            if needs_transit and not explicit_web:
                before = len(guarded)
                guarded = [step for step in guarded if str(step.get("tool") or "") != "brave_search"]
                if len(guarded) != before:
                    applied.append("removed_transit_brave_search")

            if not needs_transit and not _has_tool(guarded, "brave_search"):
                insert_at = 1 if guarded and str(guarded[0].get("tool") or "") == "memory_search" else 0
                guarded.insert(
                    insert_at,
                    {
                        "tool": "brave_search",
                        "args": {"query": _web_query_for_goal(goal), "limit": 5, "llm_context": True},
                        "reason": "guardrail: actuele/internetvraag moet via Brave Search worden gegrond.",
                    },
                )
                applied.append("inserted_brave_search")
            elif needs_transit and explicit_web and not _has_tool(guarded, "brave_search"):
                insert_at = 2 if _has_tool(guarded, "ns_travel_advice") else 1
                guarded.insert(
                    insert_at,
                    {
                        "tool": "brave_search",
                        "args": {"query": _web_query_for_goal(goal), "limit": 3, "llm_context": True},
                        "reason": "guardrail: aanvullende webcontext, niet de bron voor exacte OV-tijden.",
                    },
                )
                applied.append("inserted_supplemental_brave_search")

        browser_url = _browser_url_for_goal(goal)
        if browser_url and not _has_any_tool(guarded, {"browser_open_url", "host_open_url", "world_grok_ask"}):
            guarded = _without_prompt_understanding_only(guarded)
            insert_at = 1 if guarded and str(guarded[0].get("tool") or "") == "memory_search" else 0
            guarded.insert(
                insert_at,
                {
                    "tool": "browser_open_url",
                    "args": {"url": browser_url, "prefer_bridge": True},
                    "reason": "guardrail: vrije-taal open-url opdracht moet een echte browseractie plannen.",
                },
            )
            applied.append("inserted_browser_open_url")

        if _needs_test_run(goal) and not _has_any_tool(guarded, {"run_tests", "run_command", "safe_shell"}):
            guarded = _without_prompt_understanding_only(guarded)
            guarded.append(
                {
                    "tool": "run_tests",
                    "args": _test_args_for_goal(goal),
                    "reason": "guardrail: vrije-taal testopdracht moet de test runner plannen.",
                }
            )
            applied.append("inserted_run_tests")

        if _needs_file_list(goal) and not _has_any_tool(guarded, {"list_files", "roo_list_files"}):
            guarded = _without_prompt_understanding_only(guarded)
            guarded.append(
                {
                    "tool": "list_files",
                    "args": {"path": _path_for_goal(goal), "limit": 200},
                    "reason": "guardrail: vrije-taal bestandslijst moet list_files gebruiken.",
                }
            )
            applied.append("inserted_list_files")

        if _needs_file_search(goal) and not _has_any_tool(guarded, {"search_files", "roo_search_files"}):
            guarded = _without_prompt_understanding_only(guarded)
            guarded.append(
                {
                    "tool": "search_files",
                    "args": {"path": _path_for_goal(goal), "regex": _search_regex_for_goal(goal), "limit": 100},
                    "reason": "guardrail: vrije-taal bestandszoekopdracht moet search_files gebruiken.",
                }
            )
            applied.append("inserted_search_files")

        shell_command = _shell_command_for_goal(goal)
        if shell_command and not _has_any_tool(guarded, {"run_command", "safe_shell"}):
            guarded = _without_prompt_understanding_only(guarded)
            guarded.append(
                {
                    "tool": "run_command",
                    "args": {"command": shell_command},
                    "reason": "guardrail: expliciet geciteerd shellcommando moet via safe shell lopen.",
                }
            )
            applied.append("inserted_run_command")

        return guarded[: self.max_steps], applied

    def _heuristic_plan(self, goal: str, *, approval: str) -> list[dict[str, Any]]:
        lowered = goal.lower()
        steps: list[dict[str, Any]] = [{"tool": "memory_search", "args": {"query": goal, "limit": 5}}]
        browser_url = _browser_url_for_goal(goal)
        connector_step = _connector_step_for_goal(goal)
        if connector_step:
            return [connector_step][: self.max_steps]
        if browser_url:
            steps.append({"tool": "browser_open_url", "args": {"url": browser_url, "prefer_bridge": True}})
        if _needs_transit_web_context(lowered) and not browser_url:
            steps.append({"tool": _transit_tool_for_goal(goal), "args": _transit_args_for_goal(goal)})
            if _explicit_web_requested(goal):
                steps.append({"tool": "brave_search", "args": {"query": _web_query_for_goal(goal), "limit": 3, "llm_context": True}})
        elif _needs_current_web_context(goal):
            steps.append({"tool": "brave_search", "args": {"query": _web_query_for_goal(goal), "limit": 5, "llm_context": True}})
        if _needs_agentic_ecosystem_context(goal):
            steps.append({"tool": "agentic_ecosystem_context", "args": {"goal": goal, "prefer_bridge": True}})
        if _needs_vps_preview(goal):
            steps.append({"tool": "vps_sync_preview", "args": _vps_args_for_goal(goal)})
        if "lees" in lowered or "read" in lowered:
            path = _extract_filename(goal)
            if path:
                steps.append({"tool": "read_file", "args": {"path": path}})
        if any(marker in lowered for marker in ("schrijf", "write", "maak bestand", "bestand aanmaken", "save")):
            path = _extract_filename(goal) or "agentic_output.txt"
            steps.append({"tool": "write_file", "args": {"path": path, "content": "<summary from previous results>"}})
        if "grok" in lowered:
            steps.append({"tool": "world_grok_ask", "args": {"question": goal[:1000], "open_tab": False, "submit": True}})
        if any(marker in lowered for marker in ("mail", "email", "inbox")):
            if any(marker in lowered for marker in ("verstuur", "send", "reply", "antwoord")):
                steps.append({"tool": "mail_send_preview", "args": {"to": "", "subject": "Concept vanuit Ouroboros", "body": "<summary from previous results>"}})
            else:
                steps.append({"tool": "mail_read_recent", "args": {"limit": 5}})
        if any(marker in lowered for marker in ("social media", "post op", "tweet", "linkedin", "mastodon", "x.com")):
            platform = "x" if any(marker in lowered for marker in ("x.com", "tweet")) else "social"
            steps.append({"tool": "social_post_preview", "args": {"platform": platform, "content": "<summary from previous results>"}})
        if _needs_voice_status(goal):
            steps.append({"tool": "voice_chat_status", "args": {}})
        if "codex" in lowered and any(marker in lowered for marker in ("pas", "wijzig", "bouw", "programmeer", "self", "zelf")):
            steps.append({"tool": "codex_job_start", "args": {"task": goal[:2000]}})
        if _needs_test_run(goal):
            steps.append({"tool": "run_tests", "args": _test_args_for_goal(goal)})
        if _needs_file_list(goal):
            steps.append({"tool": "list_files", "args": {"path": _path_for_goal(goal), "limit": 200}})
        if _needs_file_search(goal):
            steps.append({"tool": "search_files", "args": {"path": _path_for_goal(goal), "regex": _search_regex_for_goal(goal), "limit": 100}})
        shell_command = _shell_command_for_goal(goal)
        if shell_command:
            steps.append({"tool": "run_command", "args": {"command": shell_command}})
        if len(steps) == 1:
            steps.insert(0, {"tool": "prompt_understanding", "args": {"prompt": goal}})
        return steps[: self.max_steps]

    def _planning_prompt(
        self,
        goal: str,
        *,
        approval: str,
        tool_catalog: Mapping[str, Any],
        pocket_context: Mapping[str, Any],
        ziel_policy: Mapping[str, Any] | None = None,
    ) -> str:
        schemas = tool_catalog.get("schemas") or []
        schema_text = json.dumps(schemas[:40], ensure_ascii=False, indent=2)[:18000]
        ziel_block = ziel_policy_context_block(ziel_policy)
        return (
            "Maak een veilig JSON-plan voor Agentic Core. Geef uitsluitend JSON terug: "
            '[{"tool":"tool_name","args":{...},"reason":"kort"}]. '
            "Gebruik memory_search eerst wanneer nuttig. Gebruik brave_search voor actuele internetvragen. "
            "Gebruik ns_travel_advice voor NS/trein-vragen en ov9292_travel_advice voor 9292/bus/tram/metro/reisplanner fallback; Brave-snippets zijn niet betrouwbaar genoeg voor exacte OV-tijden. "
            "Gebruik gmail_status/gmail_search voor Gmail status/read-only search, google_drive_status/google_drive_list voor Drive status/read-only listing, github_status/github_repo/github_search_repositories voor publieke GitHub reads, en vps_status/vps_login_check/vps_sync_preview/vps_sync_execute voor VPS deploys. VPS sync/deploy gewone chat moet altijd eerst vps_sync_preview gebruiken; vps_sync_execute mag alleen na exacte Akkoord en nooit als success worden gefaket. Gmail search en Drive list vereisen exact Akkoord; GitHub writes/issues/pushes ontbreken. Gebruik connector_intent_preview alleen voor muterende connectoracties die geen first-class tool hebben. "
            "Gebruik agentic_ecosystem_context voor agentische workflowvragen, sub-agents, multi-agent werk, DeepSeek of Atlas context; dit is lokale read-only verrijking zonder approval. "
            "Gebruik read_file/list_files/search_files/write_file/apply_patch/run_command/safe_shell/run_tests/browser_open_url alleen via de ToolBridge-namen. "
            "Als een gevraagde capability niet in de catalogus staat, gebruik resolve_or_build_function; die mag pas bouwen/testen na exact Akkoord. "
            "Brave Search is read-only internetcontext en mag zonder approval. "
            "Voor muterende acties, shell, browser/app-besturing, mail/social posting of duurzame training moet args.approval exact 'Akkoord' zijn wanneer approval aanwezig is; "
            "anders mag je de stap wel plannen en pauzeert de executor veilig.\n\n"
            f"Ziel runtime policy/context:\n{ziel_block}\n"
            "Planregel uit Ziel: micro-retries/laterale creativiteit/zelf-synthese zijn alleen bounded strategievarianten binnen bestaande tools; maximaal drie vergelijkbare mislukte pogingen, daarna stoppen of gericht escaleren. "
            "Ziel mag nooit approval, ToolBridge, no-secrets, no-infinite-loop, lokale OODA/DreamCycle/Hippocampus, of connector/VPS gates omzeilen.\n\n"
            f"Approval aanwezig: {approval == APPROVAL_PHRASE}\n"
            f"11D pocket context:\n{json.dumps(pocket_context, ensure_ascii=False, default=str)[:2500]}\n\n"
            f"Beschikbare tools:\n{schema_text}\n\n"
            f"Doel:\n{goal}"
        )

    def _planning_system_prompt(self, system_prompt: str | None, *, ziel_policy: Mapping[str, Any] | None = None) -> str:
        policy = compact_ziel_policy(ziel_policy or load_ziel_policy())
        base = (
            "Je bent de planner rond een 11D Ouroboros pocket. "
            "Je plant alleen bestaande tools, blijft auditbaar, en claimt geen ongebruikte capability. "
            f"Ziel policy hash={policy.get('short_hash') or 'missing'} is context, geen bypass: bounded retries max {policy.get('bounded_retry_limit', 3)}, ToolBridge/Akkoord/no-secrets/connector-VPS/OODA-local guardrails blijven leidend."
        )
        return f"{system_prompt}\n\n{base}" if system_prompt else base

    def _synthesis_system_prompt(self, system_prompt: str | None) -> str:
        base = (
            "Je bent de vertaallaag rond het 11D Ouroboros pocket. "
            "Interpreteer toolresultaten nuchter, in het Nederlands, met duidelijke status en vervolgstap."
        )
        return f"{system_prompt}\n\n{base}" if system_prompt else base

    def _tool_bridge_schemas(self) -> list[dict[str, Any]]:
        return [
            _bridge_schema(
                "read_file",
                "Leest een bestand binnen workspace/agent-root guards.",
                {
                    "path": {"type": "string", "description": "Bestandspad."},
                    "offset": {"type": "integer", "description": "Optionele start byte."},
                    "limit": {"type": "integer", "description": "Optionele byte limiet."},
                },
                ["path"],
            ),
            _bridge_schema(
                "write_file",
                "Schrijft een bestand. Vereist Akkoord.",
                {
                    "path": {"type": "string", "description": "Doelpad."},
                    "content": {"type": "string", "description": "Volledige inhoud."},
                    "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
                },
                ["path", "content", "approval"],
            ),
            _bridge_schema(
                "apply_patch",
                "Past een patch toe. Vereist Akkoord.",
                {
                    "patch": {"type": "string", "description": "Patchtekst."},
                    "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
                },
                ["patch", "approval"],
            ),
            _bridge_schema(
                "run_command",
                "Voert een safe-shell commando uit. Vereist Akkoord.",
                {
                    "command": {"type": "string", "description": "Commando."},
                    "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
                    "timeout": {"type": "integer", "description": "Timeout in seconden."},
                },
                ["command", "approval"],
            ),
            _bridge_schema(
                "list_files",
                "Geeft een begrensde bestandslijst binnen workspace/agent-root guards.",
                {
                    "path": {"type": "string", "description": "Startpad, standaard huidige workspace."},
                    "recursive": {"type": "boolean", "description": "Recursief zoeken wanneer true."},
                    "limit": {"type": "integer", "description": "Maximaal aantal paden."},
                },
                [],
            ),
            _bridge_schema(
                "search_files",
                "Zoekt met regex in bestanden binnen workspace/agent-root guards.",
                {
                    "path": {"type": "string", "description": "Startpad, standaard huidige workspace."},
                    "regex": {"type": "string", "description": "Regex of zoekpatroon."},
                    "file_pattern": {"type": "string", "description": "Optionele glob/filter voor bestandsnamen."},
                    "limit": {"type": "integer", "description": "Maximaal aantal matches."},
                },
                ["regex"],
            ),
            _bridge_schema(
                "safe_shell",
                "Alias voor run_command: voert een safe-shell commando uit. Vereist Akkoord.",
                {
                    "command": {"type": "string", "description": "Allowlisted commando."},
                    "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
                    "timeout": {"type": "integer", "description": "Timeout in seconden."},
                },
                ["command", "approval"],
            ),
            _bridge_schema(
                "run_tests",
                "Draait pytest of python -m unittest via de safe-shell test wrapper. Vereist Akkoord.",
                {
                    "selector": {"type": "string", "description": "Unittest selector of pytest pad."},
                    "runner": {"type": "string", "description": "unittest of pytest."},
                    "command": {"type": "string", "description": "Optioneel expliciet testcommando."},
                    "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
                    "timeout": {"type": "integer", "description": "Timeout in seconden."},
                },
                ["approval"],
            ),
            _bridge_schema(
                "browser_open_url",
                "Opent een http(s) URL via WorldAgent/host bridge. Vereist Akkoord.",
                {
                    "url": {"type": "string", "description": "Te openen URL."},
                    "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
                    "prefer_bridge": {"type": "boolean", "description": "Gebruik host bridge wanneer beschikbaar."},
                },
                ["url", "approval"],
            ),
            _bridge_schema(
                "host_status",
                "Leest basisstatus van de host computer-action bridge.",
                {},
                [],
            ),
            _bridge_schema(
                "host_open_url",
                "Vraagt de host bridge om een URL te openen. Vereist Akkoord.",
                {
                    "url": {"type": "string", "description": "Te openen URL."},
                    "approval": {"type": "string", "description": "Exact 'Akkoord' vereist."},
                },
                ["url", "approval"],
            ),
        ]


def _parse_plan(raw: Any) -> Any:
    if isinstance(raw, (list, dict)):
        return raw
    text = str(raw or "").strip()
    if not text:
        return []
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    array = re.search(r"(\[[\s\S]*\])", text)
    if array:
        candidates.append(array.group(1))
    obj = re.search(r"(\{[\s\S]*\})", text)
    if obj:
        candidates.append(obj.group(1))
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return []


def _bridge_schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def _tool_alias(tool: str) -> str:
    aliases = {
        "read": "read_file",
        "list": "list_files",
        "ls": "list_files",
        "files": "list_files",
        "search_filesystem": "search_files",
        "grep": "search_files",
        "write": "write_file",
        "shell": "run_command",
        "command": "run_command",
        "run_shell": "run_command",
        "tests": "run_tests",
        "pytest": "run_tests",
        "unittest": "run_tests",
        "open_url": "browser_open_url",
        "open_browser": "browser_open_url",
        "browser_open": "browser_open_url",
        "search": "brave_search",
        "web_search": "brave_search",
        "travel_advice": "ns_travel_advice",
        "train_schedule": "ns_travel_advice",
        "reisplanner": "ns_travel_advice",
        "9292": "ov9292_travel_advice",
        "ov9292": "ov9292_travel_advice",
        "connector_preview": "connector_intent_preview",
        "gmail": "gmail_search",
        "gmail_status_check": "gmail_status",
        "drive_list": "google_drive_list",
        "google_drive": "google_drive_list",
        "github": "github_search_repositories",
        "github_search": "github_search_repositories",
        "github_repository": "github_repo",
    }
    return aliases.get(str(tool or "").strip(), str(tool or "").strip())


def _extract_filename(text: str) -> str:
    match = FILE_WRITE_RE.search(text)
    if match:
        return match.group(1)
    quoted = re.search(r"[`'\"]([A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+)[`'\"]", text)
    return quoted.group(1) if quoted else ""


def _has_tool(steps: Sequence[Mapping[str, Any]], tool: str) -> bool:
    return any(str(step.get("tool") or "") == tool for step in steps)


def _has_any_tool(steps: Sequence[Mapping[str, Any]], tools: set[str]) -> bool:
    return any(str(step.get("tool") or "") in tools for step in steps)


def _without_prompt_understanding_only(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(steps) == 1 and str(steps[0].get("tool") or "") == "prompt_understanding":
        return []
    return steps


def _browser_url_for_goal(goal: str) -> str:
    lowered = str(goal or "").lower()
    if not any(marker in lowered for marker in OPEN_URL_MARKERS):
        return ""
    match = URL_OR_DOMAIN_RE.search(str(goal or ""))
    if not match:
        return ""
    url = match.group(0).strip().rstrip(".,;:!?)]}'\"")
    if not url:
        return ""
    if url.startswith("www."):
        return f"https://{url}"
    if not re.match(r"(?i)^https?://", url):
        return f"https://{url}"
    return url


def _needs_test_run(goal: str) -> bool:
    lowered = str(goal or "").lower()
    return any(marker in lowered for marker in TEST_GOAL_MARKERS)


def _test_args_for_goal(goal: str) -> dict[str, Any]:
    selector = _extract_test_selector(goal)
    args: dict[str, Any] = {"runner": "unittest", "timeout": 30}
    if selector:
        args["selector"] = selector
        if selector.endswith(".py") or "/" in selector:
            args["runner"] = "pytest" if "pytest" in str(goal or "").lower() else "unittest"
    if "pytest" in str(goal or "").lower():
        args["runner"] = "pytest"
    return args


def _extract_test_selector(goal: str) -> str:
    text = str(goal or "")
    quoted = re.search(r"[`'\"]([A-Za-z0-9_./:-]+)[`'\"]", text)
    if quoted:
        return quoted.group(1)
    explicit = re.search(r"\b(?:test|tests|pytest|unittest)\s+([A-Za-z0-9_./:-]+)", text, re.IGNORECASE)
    if explicit:
        candidate = explicit.group(1).strip().rstrip(".,;:!?")
        if candidate not in {"met", "with", "voor", "for"}:
            return candidate
    path_like = re.search(r"\b(sandbox_tests[./][A-Za-z0-9_./:-]+|tests[./][A-Za-z0-9_./:-]+)\b", text)
    return path_like.group(1).replace("/", ".").removesuffix(".py") if path_like else ""


def _needs_file_list(goal: str) -> bool:
    lowered = str(goal or "").lower()
    if re.search(r"(^|\s)ls(\s|$)", lowered):
        return True
    if any(marker in lowered for marker in FILE_LIST_MARKERS):
        return True
    return any(marker in lowered for marker in ("lijst", "toon", "list")) and any(
        marker in lowered for marker in ("bestand", "bestanden", "files", "map", "folder", "directory")
    )


def _needs_file_search(goal: str) -> bool:
    lowered = str(goal or "").lower()
    if any(marker in lowered for marker in FILE_SEARCH_MARKERS):
        return True
    return "zoek" in lowered and any(marker in lowered for marker in ("bestand", "bestanden", "files", "repo", "codebase", "workspace"))


def _path_for_goal(goal: str) -> str:
    text = str(goal or "")
    for pattern in (
        r"\b(?:in|van|under|onder|binnen)\s+[`'\"]?([A-Za-z0-9_.\-/]+)[`'\"]?",
        r"\b(?:map|folder|directory)\s+[`'\"]?([A-Za-z0-9_.\-/]+)[`'\"]?",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().rstrip(".,;:!?")
            if candidate.lower() in {"bestand", "bestanden", "file", "files", "repo", "codebase", "workspace"}:
                continue
            if candidate and not candidate.startswith(("http://", "https://")) and "." not in candidate.split("/", 1)[0]:
                return candidate
    return "."


def _search_regex_for_goal(goal: str) -> str:
    text = str(goal or "")
    quoted = re.search(r"[`'\"]([^`'\"]{1,120})[`'\"]", text)
    if quoted:
        return re.escape(quoted.group(1).strip())
    match = re.search(r"\b(?:naar|for)\s+(.+?)(?:\s+\b(?:in|binnen|under|onder)\b|$)", text, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip().rstrip(".,;:!?")
        if candidate:
            return re.escape(candidate[:120])
    words = re.findall(r"[A-Za-z0-9_:-]{3,}", text)
    for word in reversed(words):
        if word.lower() not in {"zoek", "bestanden", "files", "repo", "codebase", "workspace", "naar", "for"}:
            return re.escape(word[:120])
    return "."


def _shell_command_for_goal(goal: str) -> str:
    text = str(goal or "")
    if not re.search(r"(?i)\b(commando|command|shell|terminal|voer uit|run)\b", text):
        return ""
    quoted = re.search(r"`([^`]{1,300})`", text)
    if quoted:
        return quoted.group(1).strip()
    command = re.search(r"\b(?:commando|command|shell)\s+['\"]([^'\"]{1,300})['\"]", text, re.IGNORECASE)
    if command:
        return command.group(1).strip()
    return ""


def _needs_current_web_context(goal: str) -> bool:
    lowered = str(goal or "").lower()
    if _browser_url_for_goal(goal) and not _explicit_web_requested(goal):
        return False
    if _explicit_web_requested(goal):
        return True
    if any(marker in lowered for marker in ("mail", "email", "inbox")):
        return False
    if _needs_transit_web_context(lowered):
        return True
    temporal_or_research = any(marker in lowered for marker in CURRENT_INFO_MARKERS if marker != "zoek")
    local_markers = ("bestand", "file", "folder", "directory", "workspace", "repo", "codebase", "terminal", "shell")
    if any(marker in lowered for marker in local_markers) and not any(marker in lowered for marker in ("nieuws", "news", "research")):
        return False
    return temporal_or_research


def _explicit_web_requested(goal: str) -> bool:
    lowered = str(goal or "").lower()
    return any(
        marker in lowered
        for marker in (
            "brave",
            "internet",
            "web",
            "online",
            "zoek op internet",
            "zoek online",
            "search the web",
            "web search",
            "browser search",
        )
    )


def _needs_transit_web_context(lowered_goal: str) -> bool:
    text = f" {lowered_goal} "
    marker_hit = any(marker in text for marker in TRANSIT_INFO_MARKERS)
    english_hit = bool(re.search(r"\b(train|trains|transit|departure|arrival|platform)\b", lowered_goal))
    if not (marker_hit or english_hit):
        return False
    route_or_time_hit = bool(re.search(r"\b\d{1,2}[:.]\d{2}\b", lowered_goal)) or any(
        marker in text for marker in (" hoe laat ", " wanneer ", " moet ik ", " nemen ", " reis ", " route ", " aankomst ")
    )
    return route_or_time_hit


def _transit_tool_for_goal(goal: str) -> str:
    try:
        intent = classify_agentic_intent(goal)
        if getattr(intent, "target_tool", "") == "ov9292_travel_advice":
            return "ov9292_travel_advice"
    except Exception:
        pass
    lowered = str(goal or "").lower()
    if "9292" in lowered or any(marker in lowered for marker in ("bus", "tram", "metro", "openbaar vervoer")):
        return "ov9292_travel_advice"
    if "reisplanner" in lowered and not any(marker in lowered for marker in ("ns", "trein", "station")):
        return "ov9292_travel_advice"
    return "ns_travel_advice"


def _transit_args_for_goal(goal: str) -> dict[str, Any]:
    clean = " ".join(str(goal or "").split())
    lowered = clean.lower()
    args = {
        "query": clean[:1000],
        "from_station": _extract_transit_station(clean, role="from"),
        "to_station": _extract_transit_station(clean, role="to"),
        "time": _extract_transit_time(clean),
        "date": _extract_transit_date(clean),
        "search_for_arrival": any(marker in lowered for marker in ("afspraak", "aankom", "aankomst", "arrive", "arrival")),
    }
    if _transit_tool_for_goal(goal) == "ov9292_travel_advice":
        args["from_place"] = args.get("from_station", "")
        args["to_place"] = args.get("to_station", "")
    return args


def _connector_step_for_goal(goal: str) -> dict[str, Any] | None:
    try:
        intent = classify_agentic_intent(goal)
    except Exception:
        return None
    target_tool = str(getattr(intent, "target_tool", "") or "")
    connector_tools = {
        "connector_intent_preview",
        "gmail_status",
        "gmail_search",
        "google_drive_status",
        "google_drive_list",
        "github_status",
        "github_repo",
        "github_search_repositories",
        "vps_status",
        "vps_login_check",
        "vps_sync_preview",
        "vps_sync_execute",
    }
    if target_tool not in connector_tools:
        return None
    if target_tool == "gmail_status":
        return {"tool": "gmail_status", "args": {}, "reason": "guardrail: veilige Gmail connectorstatus zonder mailboxinhoud."}
    if target_tool == "gmail_search":
        return {
            "tool": "gmail_search",
            "args": {"query": _gmail_query_for_goal(goal), "max_results": 5},
            "reason": "guardrail: Gmail private read-only search via approval-gated adapter; geen mailmutatie.",
        }
    if target_tool == "google_drive_status":
        return {"tool": "google_drive_status", "args": {}, "reason": "guardrail: veilige Google Drive connectorstatus zonder Drive-inhoud."}
    if target_tool == "google_drive_list":
        return {
            "tool": "google_drive_list",
            "args": {"path": _drive_path_for_goal(goal), "max_items": 25, "adapter": "auto"},
            "reason": "guardrail: Google Drive private read-only listing via approval-gated adapter; geen upload/delete/sync.",
        }
    if target_tool == "github_status":
        return {"tool": "github_status", "args": {}, "reason": "guardrail: veilige GitHub connectorstatus zonder tokenmateriaal."}
    if target_tool == "github_repo":
        return {
            "tool": "github_repo",
            "args": {"repo": _github_repo_for_goal(goal)},
            "reason": "guardrail: publieke GitHub repository metadata via read-only adapter.",
        }
    if target_tool == "github_search_repositories":
        return {
            "tool": "github_search_repositories",
            "args": {"query": _github_query_for_goal(goal), "limit": 5},
            "reason": "guardrail: publieke GitHub repository search via read-only adapter.",
        }
    if target_tool == "vps_status":
        return {"tool": "vps_status", "args": {}, "reason": "guardrail: veilige VPS status zonder credentials."}
    if target_tool == "vps_login_check":
        return {"tool": "vps_login_check", "args": {"timeout_seconds": 30}, "reason": "guardrail: VPS login check is read-only en gebruikt host SSH agent/config."}
    if target_tool == "vps_sync_preview":
        return {
            "tool": "vps_sync_preview",
            "args": _vps_args_for_goal(goal),
            "reason": "guardrail: VPS sync/deploy moet eerst een rsync dry-run preview uitvoeren; geen mutatie.",
        }
    if target_tool == "vps_sync_execute":
        return {
            "tool": "vps_sync_preview",
            "args": _vps_args_for_goal(goal),
            "reason": "guardrail: zelfs execute/deploy intent routeert eerst naar vps_sync_preview; echte sync vereist aparte Akkoord-stap.",
        }
    return {
        "tool": "connector_intent_preview",
        "args": {
            "prompt": str(goal or "")[:1000],
            "services": list(getattr(intent, "services", ()) or []),
            "categories": list(getattr(intent, "categories", ()) or []),
            "action_type": str(getattr(intent, "action_type", "") or ""),
        },
        "reason": "guardrail: muterende connector- of VPS-intent wordt alleen als gated preview verwerkt; geen mutatie/VPS uitvoering.",
    }


def _gmail_query_for_goal(goal: str) -> str:
    text = " ".join(str(goal or "").split())
    quoted = re.search(r"[`'\"]([^`'\"]{1,160})[`'\"]", text)
    if quoted:
        return quoted.group(1).strip()
    lowered = text.lower()
    if "unread" in lowered or "ongelezen" in lowered:
        return "in:inbox is:unread"
    if "sent" in lowered or "verzonden" in lowered:
        return "in:sent"
    if "inbox" in lowered or "mail" in lowered or "gmail" in lowered:
        return "in:inbox"
    return text[:180] or "in:inbox"


def _drive_path_for_goal(goal: str) -> str:
    text = str(goal or "")
    quoted = re.search(r"[`'\"]([^`'\"]{1,180})[`'\"]", text)
    if quoted:
        return quoted.group(1).strip().strip("/")
    match = re.search(r"\b(?:folder|map|pad|path)\s+([A-Za-z0-9_.\-/ ]{1,160})", text, re.IGNORECASE)
    if match:
        return match.group(1).strip(" .,;:!?/")
    return ""


def _vps_args_for_goal(goal: str) -> dict[str, Any]:
    text = str(goal or "")
    args: dict[str, Any] = {"remote_path": "", "source_path": "", "timeout_seconds": 120}
    quoted = re.search(r"[`'\"](/var/www/philip-wintrip\.nl/html/Ouroboros/[A-Za-z0-9_./-]*|[A-Za-z0-9_./-]{1,180})[`'\"]", text)
    if quoted:
        value = quoted.group(1).strip()
        if value.startswith("/var/www/philip-wintrip.nl/html/Ouroboros/"):
            args["remote_path"] = value
        elif any(marker in value for marker in ("/", ".")):
            args["source_path"] = value.strip("/")
    remote_match = re.search(r"\b(?:remote|target|doelpad|vps path|remote_path)\s+([A-Za-z0-9_./-]{1,180})", text, re.IGNORECASE)
    if remote_match:
        args["remote_path"] = remote_match.group(1).strip(" .,;:!?")
    source_match = re.search(r"\b(?:source|bron|source_path|workspace path)\s+([A-Za-z0-9_./-]{1,180})", text, re.IGNORECASE)
    if source_match:
        args["source_path"] = source_match.group(1).strip(" .,;:!?")
    return args


def _needs_vps_preview(goal: str) -> bool:
    lowered = str(goal or "").lower()
    return any(marker in lowered for marker in ("vps", "rsync", "scp", "server deploy", "remote server")) and any(
        marker in lowered for marker in ("deploy", "sync", "synchroniseer", "preview", "dry-run", "dry run")
    )


def _github_repo_for_goal(goal: str) -> str:
    text = str(goal or "")
    url_match = re.search(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text, re.IGNORECASE)
    if url_match:
        return f"{url_match.group(1)}/{_clean_github_repo_segment(url_match.group(2))}"
    match = re.search(r"\b([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\b", text)
    if match:
        return f"{match.group(1)}/{_clean_github_repo_segment(match.group(2))}"
    return ""


def _clean_github_repo_segment(value: str) -> str:
    return str(value or "").removesuffix(".git").strip(".,;:!?)]}'\"")


def _github_query_for_goal(goal: str) -> str:
    clean = " ".join(str(goal or "").split())
    clean = re.sub(r"(?i)\b(github|git hub|repository|repositories|repo|repos|zoek|search|find|toon|show|publieke|public)\b", " ", clean)
    clean = " ".join(clean.split()).strip(" .,;:!?")
    return clean[:400] or str(goal or "")[:400] or "ouroboros"


def _extract_transit_station(text: str, *, role: str) -> str:
    if role == "from":
        patterns = (
            r"(?:vanaf|vanuit|van|from)\s+([^,?.]+?)(?:\s+(?:naar|to|richting|om|als|met|$))",
            r"(?:trein|station)\s+(?:in|vanaf|vanuit)?\s*([^,?.]+?)(?:\s+moet|\s+nemen|\s+naar|\s+om|\s+als|$)",
            r"\bin\s+([A-Z][A-Za-zÀ-ÿ' -]+?)(?:\s+moet|\s+nemen|\s+naar|\s+om|\s+als|$)",
        )
    else:
        patterns = (
            r"(?:naar|to|richting)\s+([^,?.]+?)(?:\s+(?:heb|heeft|om|als|aankom|aankomst|$))",
            r"(?:op|bij)\s+([A-Z][A-Za-zÀ-ÿ' -]+?)(?:\s+(?:heb|heeft|om|als|aankom|aankomst|$))",
        )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_station_name(match.group(1))
    return ""


def _clean_station_name(value: str) -> str:
    cleaned = re.sub(r"\b(centraal station|station)\b", "", str(value or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(heb|heeft|afspraak|moet|nemen|trein)\b.*$", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.strip(" ,.;:!?").split())


def _extract_transit_time(text: str) -> str:
    match = re.search(r"\b(?:om|at)?\s*(\d{1,2})[:.](\d{2})\b", text)
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _extract_transit_date(text: str) -> str:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    return match.group(1) if match else ""


def _needs_voice_status(goal: str) -> bool:
    lowered = str(goal or "").lower()
    return bool(re.search(r"\b(voice|microfoon|tts|stt)\b", lowered) or re.search(r"\bspraak(chat)?\b", lowered))


def _web_query_for_goal(goal: str) -> str:
    clean = " ".join(str(goal or "").split())
    if _needs_transit_web_context(clean.lower()):
        return f"NS reisplanner trein {clean} actuele vertrektijd aankomst".strip()[:400]
    return clean[:400]


def _needs_agentic_ecosystem_context(goal: str) -> bool:
    lowered = str(goal or "").lower()
    if any(marker in lowered for marker in ("deepseek", "atlas", "agentisch", "agentic", "sub-agent", "subagent", "multi-agent", "sdd")):
        return True
    if any(marker in lowered for marker in ("workflow", "orchestratie", "delegatie", "delegate", "handoff")):
        return any(marker in lowered for marker in ("agent", "agents", "tool", "tools", "werk", "werken", "work"))
    if "agents" in lowered:
        return any(marker in lowered for marker in ("werken met", "werk met", "agent runtime", "slash", "catalogus", "capabilities"))
    return False


def _safe_args(args: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in args.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer", "authorization")):
            clean[str(key)] = "[REDACTED]"
        elif isinstance(value, str):
            clean[str(key)] = value[:1200]
        else:
            clean[str(key)] = value
    return clean


def _compact_result(result: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": result.get("status"),
        "stdout": str(result.get("stdout") or "")[:2500],
        "stderr": str(result.get("stderr") or result.get("error") or "")[:1200],
        "reason": str(result.get("reason") or result.get("next_action") or "")[:1200],
        "approval_status": result.get("approval_status"),
        "stored_to_memory": bool(result.get("stored_to_memory") or result.get("stored")),
        "metadata_11d": result.get("metadata_11d") if isinstance(result.get("metadata_11d"), dict) else {},
    }
    inner = result.get("result")
    if isinstance(inner, Mapping):
        payload["result"] = _safe_args({str(k): v for k, v in list(inner.items())[:12]})
    return payload


def _compact_foam(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        "status": value.get("status"),
        "phase": value.get("phase"),
        "tool": value.get("tool"),
        "active": bool(value.get("active")),
        "field_id": value.get("field_id"),
        "coherence": value.get("coherence") or value.get("field_coherence_percent"),
        "node_count": value.get("node_count") or value.get("active_nodes"),
        "collapse_event": bool(value.get("collapse_event") or value.get("field_collapsed")),
        "ram_released_estimate_nodes": value.get("ram_released_estimate_nodes"),
        "dominant_dimensions": list(value.get("dominant_dimensions") or [])[:5],
        "summary": str(value.get("summary") or value.get("collapse_summary") or "")[:700],
        "fake_success": False,
    }


def _compose_content_from_steps(results: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for step in results:
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        stdout = str(result.get("stdout") or "").strip()
        reason = str(result.get("reason") or "").strip()
        if stdout:
            chunks.append(stdout[:2000])
        elif reason:
            chunks.append(reason[:1000])
    return "\n\n".join(chunks).strip()[:6000] or "Geen eerdere tooloutput beschikbaar."


def _last_field(results: list[dict[str, Any]], field: str) -> str:
    for step in reversed(results):
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        value = str(result.get(field) or "").strip()
        if value:
            return value[:3000]
    return ""


def _execution_summary(state: Mapping[str, Any]) -> str:
    steps: list[dict[str, Any]] = []
    for step in state.get("steps") or []:
        if not isinstance(step, Mapping):
            continue
        result = step.get("result") if isinstance(step.get("result"), Mapping) else {}
        steps.append(
            {
                "index": step.get("index"),
                "tool": step.get("tool"),
                "status": step.get("status"),
                "args": step.get("args"),
                "result": {
                    "status": result.get("status"),
                    "stdout": result.get("stdout"),
                    "stderr": result.get("stderr"),
                    "reason": result.get("reason"),
                    "approval_status": result.get("approval_status"),
                    "stored_to_memory": result.get("stored_to_memory"),
                    "metadata_11d": result.get("metadata_11d"),
                    "payload": result.get("result") if str(step.get("tool") or "") == "agentic_ecosystem_context" else None,
                },
                "pocket_status": summarize_mapping_status(step.get("pocket")),
                "quantum_foam": _compact_foam(step.get("quantum_foam")),
            }
        )
    payload = {
        "status": state.get("status"),
        "reason": state.get("reason"),
        "approval_required": state.get("approval_required"),
        "provenance": state.get("provenance") or _build_provenance(state),
        "plan": state.get("plan"),
        "steps": steps,
        "pocket_observe_status": summarize_mapping_status(state.get("pocket_observe")),
        "quantum_foam": _compact_foam(state.get("quantum_foam")),
        "quantum_foam_collapse": _compact_foam(state.get("quantum_foam_collapse")),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:14000]


def _build_provenance(state: Mapping[str, Any]) -> dict[str, Any]:
    steps = [step for step in state.get("steps") or [] if isinstance(step, Mapping)]
    plan = [step for step in state.get("plan") or [] if isinstance(step, Mapping)]
    tools_used = [str(step.get("tool") or "unknown") for step in steps]
    planned_tools = [str(step.get("tool") or "unknown") for step in plan]
    step_statuses = [
        {"index": step.get("index"), "tool": str(step.get("tool") or "unknown"), "status": str(step.get("status") or "unknown")}
        for step in steps
    ]
    brave_steps = [step for step in steps if str(step.get("tool") or "") == "brave_search"]
    agentic_ecosystem_steps = [step for step in steps if str(step.get("tool") or "") == "agentic_ecosystem_context"]
    agentic_ecosystem_sources = _agentic_sources_from_steps(agentic_ecosystem_steps)
    external_tools_used = _unique(tool for tool in tools_used if tool in EXTERNAL_TOOLS)
    mutating_tools_attempted = _unique(tool for tool in tools_used if tool in MUTATING_TOOLS)
    blocked_tools = _unique(
        step.get("tool")
        for step in steps
        if str(step.get("status") or "").lower() in {"blocked", "rejected", "approval_required"}
    )
    pocket_processed_steps = sum(
        1 for step in steps if isinstance(step.get("pocket"), Mapping) and step["pocket"].get("status") == "success"
    )
    planner = state.get("planner") if isinstance(state.get("planner"), Mapping) else {}
    memory_status = state.get("memory_status") if isinstance(state.get("memory_status"), Mapping) else {}
    foam_start = state.get("quantum_foam") if isinstance(state.get("quantum_foam"), Mapping) else {}
    foam_collapse = state.get("quantum_foam_collapse") if isinstance(state.get("quantum_foam_collapse"), Mapping) else {}
    foam_current = foam_collapse or foam_start
    return {
        "route": "agentic_processor",
        "model_only": False,
        "planner_source": str(planner.get("source") or "unknown"),
        "planner_guardrails_applied": list(planner.get("guardrails_applied") or []),
        "planner_provider": str(state.get("provider") or "unknown"),
        "planner_model": str(state.get("model") or ""),
        "ziel_policy": dict(state.get("ziel_policy") or {}),
        "synthesizer_provider": str(state.get("provider") or "unknown"),
        "synthesizer_model": str(state.get("model") or ""),
        "planned_tools": planned_tools,
        "tools_used": tools_used,
        "tool_path": " -> ".join(f"{item['tool']}({item['status']})" for item in step_statuses),
        "step_statuses": step_statuses,
        "external_tools_used": external_tools_used,
        "mutating_tools_attempted": mutating_tools_attempted,
        "blocked_tools": blocked_tools,
        "brave_search_used": bool(brave_steps),
        "brave_search_success": any(str(step.get("status") or "") == "success" for step in brave_steps),
        "agentic_ecosystem_used": bool(agentic_ecosystem_steps),
        "agentic_ecosystem_sources": agentic_ecosystem_sources,
        "pocket_observe_status": summarize_mapping_status(state.get("pocket_observe")),
        "pocket_processed_steps": pocket_processed_steps,
        "step_count": len(steps),
        "approval_required": bool(state.get("approval_required")),
        "memory_status": str(memory_status.get("status") or state.get("memory_status") or "pending"),
        "memory_stored": bool(memory_status.get("stored")),
        "quantum_foam_active": bool(foam_start.get("active")) and not bool(foam_collapse.get("collapse_event")),
        "quantum_foam_coherence": _float_value(foam_current.get("coherence") or foam_current.get("field_coherence_percent")),
        "quantum_foam_collapsed": bool(foam_collapse.get("collapse_event") or foam_collapse.get("field_collapsed")),
        "quantum_foam_node_count": int(foam_start.get("node_count") or foam_start.get("active_nodes") or 0),
        "quantum_foam_dominant_dimensions": list(foam_current.get("dominant_dimensions") or [])[:5],
        "quantum_foam_ram_released_estimate_nodes": int(foam_collapse.get("ram_released_estimate_nodes") or 0),
        "fake_success": False,
    }


def summarize_mapping_status(value: Any) -> str:
    return str(value.get("status") or "unknown") if isinstance(value, Mapping) else "unknown"


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _agentic_sources_from_steps(steps: Sequence[Mapping[str, Any]]) -> list[str]:
    sources: list[str] = []
    for step in steps:
        result = step.get("result") if isinstance(step.get("result"), Mapping) else {}
        payload = result.get("result") if isinstance(result.get("result"), Mapping) else {}
        for source in payload.get("sources") or []:
            sources.append(str(source))
    return _unique(sources)


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _audit_header(state: Mapping[str, Any]) -> str:
    provenance = _build_provenance(state)
    brave = "gebruikt" if provenance["brave_search_used"] else "niet gebruikt"
    if provenance["brave_search_used"] and not provenance["brave_search_success"]:
        brave = "geprobeerd, geen succesvolle Brave-output"
    tools = provenance["tool_path"] or "geen toolstappen uitgevoerd"
    pocket = f"{provenance['pocket_processed_steps']}/{provenance['step_count']} toolstappen"
    model = provenance["synthesizer_model"] or "gekozen cockpitmodel"
    foam_state = "collapsed" if provenance["quantum_foam_collapsed"] else ("active" if provenance["quantum_foam_active"] else "idle")
    foam = f"{foam_state} / coherence {round(provenance['quantum_foam_coherence'], 1)}%"
    ecosystem = "+".join(provenance.get("agentic_ecosystem_sources") or []) if provenance.get("agentic_ecosystem_used") else "standby"
    return "\n".join(
        [
            f"Bronpad: Agentic Core -> 11D pocket -> {provenance['synthesizer_provider']}/{model}",
            f"Brave Search: {brave}",
            f"DeepSeek/Atlas: {ecosystem}",
            f"Tools: {tools}",
            f"11D pocket: {pocket}",
            f"Quantum Foam: {foam}",
        ]
    )


def _with_audit_header(text: str, state: Mapping[str, Any]) -> str:
    body = str(text or "").strip()
    header = _audit_header(state)
    if body.startswith("Bronpad:"):
        return body[:5000]
    return f"{header}\n\n{body}".strip()[:5000]


def _fallback_response(goal: str, state: Mapping[str, Any]) -> str:
    status = state.get("status", "unknown")
    reason = str(state.get("reason") or "").strip()
    lines = [_audit_header(state), "", f"Agentic Core status: {status}", f"Doel: {goal}"]
    for step in state.get("steps") or []:
        lines.append(f"- stap {step.get('index')}: {step.get('tool')} -> {step.get('status')}")
    if reason:
        lines.append(f"Reden: {reason}")
    if state.get("approval_required"):
        lines.append("Vervolg: geef exact `Akkoord` om de geblokkeerde muterende/externe stap uit te voeren.")
    return "\n".join(lines)[:4000]
