# Ouroboros IDE Context

Doel: WintripAI, Ruflo, Roo en Codex moeten hetzelfde lokale systeembeeld delen wanneer ze in de IDE verder aan Ouroboros coderen.

## Roots

- WintripAI workspace: `/home/pwintri2/WintripAI`
- Docker workspace: `/workspace`
- Ruflo workspace: `/home/pwintri2/ruflo`
- Roo workspace: `/home/pwintri2/Roo-code`
- Codex workspace: `/home/pwintri2/Codex`
- DeepSeek workspace: `/home/pwintri2/deepseek`
- Atlas workspace: `/home/pwintri2/atlas`

## Runtime Context

- Cockpit chat endpoint: `POST /api/cockpit/chat`
- Cockpit slash agents: `/codex`, `/deepseek`, `/atlas`, `/ruflo`, `/claude`, `/roo`, `/agents`
- Server-side chat memory: `.secrets/ouroboros_self_context.json`
- Self-context status: `GET /api/ouroboros/self-context/status`
- Host agent bridge: `POST /agents/command` via `scripts/rclone_host_bridge.py`
- Ruflo host bridge status: `GET /ruflo/status` via `scripts/rclone_host_bridge.py`
- Roo local tool adapter: `controller/roo_tools.py`
- Codex registry adapter: `controller/codex_registry.py`

## Agent Contract

- Treat WintripAI as the authoritative Ouroboros project root.
- Treat Ruflo as the neighbouring orchestration/agent workspace.
- Keep chat continuity server-side; do not rely on browser history alone.
- Never store API keys, OAuth tokens or bearer secrets verbatim in long-term memory.
- File edits still require the project approval phrase where the backend asks for it: `Akkoord`.

## Practical Paths

- From WintripAI to Ruflo: use absolute path `/home/pwintri2/ruflo`, or Roo alias `ruflo/...` when the root is visible.
- From Ruflo back to WintripAI: see `/home/pwintri2/ruflo/WINTRIPAI_CONTEXT.md`.
- From Docker backend to host Ruflo: use the host bridge self-context status instead of assuming `/home/pwintri2/ruflo` is mounted inside the container.
- From Docker backend to host DeepSeek/Atlas: use the host bridge for CLI execution; mounted `/deepseek` and `/atlas` are read-only context roots.
