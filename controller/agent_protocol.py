from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List

PROTOCOL_VERSION = "WINTRIP-AGENT/1.0"


@dataclass
class AgentScope:
    owned_paths: List[str] = field(default_factory=list)
    read_paths: List[str] = field(default_factory=list)
    write_paths: List[str] = field(default_factory=list)


@dataclass
class AgentEnvelope:
    agent: str
    task_id: str
    type: str
    summary: str
    scope: AgentScope
    inputs: List[Any] = field(default_factory=list)
    outputs: List[Any] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    needs_review: bool = True
    requires_human: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["protocol"] = PROTOCOL_VERSION
        return data


def make_envelope(
    *,
    agent: str,
    task_id: str,
    type: str,
    summary: str,
    owned_paths: List[str],
    read_paths: List[str] | None = None,
    write_paths: List[str] | None = None,
    inputs: List[Any] | None = None,
    outputs: List[Any] | None = None,
    risks: List[str] | None = None,
    needs_review: bool = True,
    requires_human: bool = False,
) -> Dict[str, Any]:
    envelope = AgentEnvelope(
        agent=agent,
        task_id=task_id,
        type=type,
        summary=summary,
        scope=AgentScope(
            owned_paths=owned_paths,
            read_paths=read_paths or [],
            write_paths=write_paths or [],
        ),
        inputs=inputs or [],
        outputs=outputs or [],
        risks=risks or [],
        needs_review=needs_review,
        requires_human=requires_human,
    )
    return envelope.to_dict()
