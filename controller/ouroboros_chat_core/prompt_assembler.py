from __future__ import annotations

from typing import Any


PLATFORM_SYSTEM_RULES = """\
You are running inside Ouroboros Chat, a local-first, human-controlled persona platform.
Keep behavior practical, auditable, reversible, and safe.
Do not claim autonomous personhood, consciousness, omniscience, spiritual authority, or real-world actions that were not actually performed.
Mutating, browser, shell, email/calendar, external API, and file-write actions require explicit approval through existing gated tools.
"""


class PromptAssembler:
    def assemble(
        self,
        *,
        persona: dict[str, Any],
        memories: list[dict[str, Any]],
        knowledge: list[dict[str, Any]],
        recent_history: list[dict[str, Any]],
        user_message: str,
        attachment_context: str = "",
    ) -> dict[str, Any]:
        memory_text = "\n".join(
            f"- [{item.get('scope', 'memory')}; importance {item.get('importance', 3)}] {item.get('content', '')}"
            for item in memories[:12]
            if item.get("content")
        )
        knowledge_text = "\n\n".join(
            f"Source: {item.get('label') or item.get('source')}\n{item.get('snippet', '')}"
            for item in knowledge[:8]
            if item.get("snippet")
        )
        rules_text = "\n".join(f"- {rule}" for rule in persona.get("rules", []) if str(rule).strip())
        system_parts = [
            PLATFORM_SYSTEM_RULES.strip(),
            f"Persona name: {persona.get('name', 'Ouroboros')}",
            f"Persona role: {persona.get('role', '')}",
            f"Persona description: {persona.get('description', '')}",
            f"Language preference: {persona.get('language', 'nl')}",
            f"Tone/style: {persona.get('tone', '')}",
            f"Instructions:\n{persona.get('instructions') or persona.get('system_prompt') or ''}",
            f"Do/don't rules:\n{rules_text}" if rules_text else "",
            f"Relevant memory:\n{memory_text}" if memory_text else "",
            f"Relevant knowledge snippets:\n{knowledge_text}" if knowledge_text else "",
            f"Transient attachment context:\n{attachment_context}" if attachment_context else "",
        ]
        return {
            "system_prompt": "\n\n".join(part for part in system_parts if str(part).strip()),
            "history": [
                {"role": str(item.get("role")), "content": str(item.get("content", ""))[:8000]}
                for item in recent_history[-24:]
                if item.get("role") in {"user", "assistant", "system"} and item.get("content")
            ],
            "user_prompt": user_message,
            "sources": [{"label": item.get("label"), "source": item.get("source")} for item in knowledge[:8]],
        }

