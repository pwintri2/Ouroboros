# WintripAI Agent Guide

Read `OUROBOROS_IDE_CONTEXT.md` first. This repository is the authoritative implementation workspace for the Ouroboros experiment.

## Shared Roots

- WintripAI: `/home/pwintri2/WintripAI`
- Docker runtime: `/workspace`
- Ruflo: `/home/pwintri2/ruflo`
- Roo: `/home/pwintri2/Roo`
- Codex: `/home/pwintri2/Codex`

## Continuity

Cockpit chat memory is server-side in `.secrets/ouroboros_self_context.json` via `controller/ouroboros_self_context.py`. Agents should treat that memory as the current continuity layer and avoid depending on browser chat history alone.

## Slash Agents

The cockpit chat routes slash-prefixed prompts through `controller/slash_agent_router.py`:

- `/codex <task>` runs Codex CLI against WintripAI through the host bridge.
- `/ruflo <task>` starts Ruflo swarm coordination through the host bridge.
- `/claude <task>` runs Claude Code through the host bridge when Claude auth is present.
- `/roo <task>` uses the Roo Python adapter or writes a Roo handoff task.
- `/agents` shows the catalog.

## Guardrails

Do not store API keys, OAuth tokens, bearer tokens, passwords or browser session material in long-term memory or context files. When backend tools ask for approval, the exact phrase is `Akkoord`.
