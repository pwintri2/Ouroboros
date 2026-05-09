# WintripAI Agent Guide

Read `OUROBOROS_IDE_CONTEXT.md` first. This repository is the authoritative implementation workspace for the Ouroboros experiment.

## Shared Roots

- WintripAI: `/home/pwintri2/WintripAI`
- Docker runtime: `/workspace`
- Ruflo: `/home/pwintri2/ruflo`
- Roo: `/home/pwintri2/Roo-code`
- Codex: `/home/pwintri2/Codex`
- DeepSeek: `/home/pwintri2/deepseek`
- Atlas: `/home/pwintri2/atlas`

## Continuity

Cockpit chat memory is server-side in `.secrets/ouroboros_self_context.json` via `controller/ouroboros_self_context.py`. Agents should treat that memory as the current continuity layer and avoid depending on browser chat history alone.

## Slash Agents

The cockpit chat routes slash-prefixed prompts through `controller/slash_agent_router.py`:

- `/codex <task>` runs Codex CLI against WintripAI through the host bridge.
- `/deepseek <task>` runs DeepSeek `exec --auto --json` against WintripAI when the CLI is launchable.
- `/atlas <task>` runs Atlas `ask` against WintripAI when the CLI is launchable.
- `/ruflo <task>` starts Ruflo swarm coordination through the host bridge.
- `/claude <task>` runs Claude Code through the host bridge when Claude auth is present.
- `/roo <task>` uses safe Roo Python read/list/search adapters or starts a Roo Code CLI agent-runtime job with the Cockpit-selected model. Local selections route to Ollama; supported cloud selections route through the API key stored in Cockpit for that provider.
- `/agents` shows the catalog.

## Guardrails

Do not store API keys, OAuth tokens, bearer tokens, passwords or browser session material in long-term memory or context files. When backend tools ask for approval, the exact phrase is `Akkoord`.
