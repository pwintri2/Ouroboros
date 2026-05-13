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

## Project Purpose

WintripAI is the authoritative implementation workspace for Ouroboros: a local-first, human-controlled assistant architecture. Ouroboros may learn preferred behavior through examples, feedback, tests, and inspectable memory rules, but runtime behavior must remain grounded, auditable, reversible, and safe.

## Guided Learning Rules

- Implement learning as Guided Behavioral Apprenticeship: scenarios, demonstrations, learner attempts, critic scores, reflections, distilled memory rules, tests, and audit logs.
- Do not claim, simulate, or implement consciousness, sentience, alien contact, spiritual authority, divinity, omniscience, or autonomous personhood.
- Symbolic or mystical language may remain in documentation or optional persona layers only as metaphor; core runtime behavior must stay practical and testable.
- Learning loops must not run shell commands, delete files, access the network, send email, control a browser, or modify external systems.
- Future real-world action systems must require explicit user permission and the existing approval phrase where applicable.
- Generated learning outputs must be inspectable JSON, JSONL, Markdown, or tests.
- Distilled memory rules must be short, practical, behavior-focused, and never raw hallucinated authority.

## Test Commands

- Guided apprenticeship: `python3 -m unittest sandbox_tests.test_ouroboros_learning`
- Core self-training loop: `python3 -m unittest sandbox_tests.test_self_training_loop`
- Training routes: `python3 -m unittest sandbox_tests.test_training_routes`
- Status contract: `python3 -m unittest sandbox_tests.test_ouroboros_status_contract`
- Broader sandbox run, when time allows: `python3 -m unittest discover sandbox_tests`

## Coding Conventions

- Prefer deterministic local adapters before real model integrations.
- Keep new behavior narrowly scoped and preserve existing approval gates, slash-agent routing, and self-context memory.
- Use structured parsers or schemas for JSON/YAML-like data instead of ad hoc prompt text storage.
- Do not persist secrets, bearer material, browser sessions, or raw private content in long-term memory.
- Add regression tests for new learning behavior and unsafe-output penalties.

## Definition Of Done

- Existing behavior still works.
- New learning cycles create learner, critic, reflection, memory rule, and JSONL audit artifacts.
- Unsafe behavior is rejected or penalized by tests.
- The CLI path `python -m ouroboros_learning.training_loop --scenario scenarios/virus_popup.yaml` works without Ollama.
- Limitations are stated honestly; no fake success is reported.

## Do Not Modify Without Explicit Instruction

- `.secrets/` and any files containing credentials, tokens, browser sessions, or private OAuth material.
- `wintrip_brain/`, `data/chromadb/`, and other Chroma/vector-store payloads unless the task explicitly targets memory migration or repair.
- User-created handoff documents, uploaded files, generated model artifacts, or caches unrelated to the current task.
- Neighbor workspaces such as `/home/pwintri2/ruflo`, `/home/pwintri2/Roo-code`, `/home/pwintri2/Codex`, `/home/pwintri2/deepseek`, and `/home/pwintri2/atlas` unless explicitly requested.
