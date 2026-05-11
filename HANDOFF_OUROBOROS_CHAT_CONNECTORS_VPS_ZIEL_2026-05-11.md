# Handoff: Ouroboros chat connectors, VPS sync, and Ziel policy

Date: 2026-05-11

Branch: feature/ouroboros-chat-connectors-vps-ziel

Base branch at handoff start: feature/esoteric-ouroboros-architecture

Base commit at handoff start: 92f3535902fd7b1c868d764c4b53babfeae35fab

Commit: local commit to be created after this handoff file is staged; exact hash reported in completion

Remote: origin https://github.com/pwintri2/wintripai.git

## Summary

This handoff covers the ordinary-cockpit-chat Ouroboros upgrade that adds guarded agent and action selection, safe public internet/travel lookup routing, a foundation for Gmail, Google Drive, GitHub, and VPS connector actions, safe VPS sync plumbing, and first-class Ziel policy visibility in runtime context and status surfaces.

The implementation keeps OODA, Hippocampus, and DreamCycle local-only boundaries intact. No real SSH, rsync execute, Gmail, Google Drive, or GitHub network operation was run during validation.

## In-scope files changed

Core chat and tool orchestration:

- [controller/agentic_intent.py](controller/agentic_intent.py)
- [controller/main.py](controller/main.py)
- [controller/agentic_processor.py](controller/agentic_processor.py)
- [controller/agent_tools.py](controller/agent_tools.py)
- [controller/api_key_store.py](controller/api_key_store.py)

Connector and deployment foundation:

- [controller/github_adapter.py](controller/github_adapter.py)
- [controller/vps_deploy_adapter.py](controller/vps_deploy_adapter.py)
- [scripts/rclone_host_bridge.py](scripts/rclone_host_bridge.py)

Ziel policy and runtime/status integration:

- [controller/ziel_policy.py](controller/ziel_policy.py)
- [controller/ouroboros_self_context.py](controller/ouroboros_self_context.py)
- [controller/ouroboros_status.py](controller/ouroboros_status.py)
- [controller/runtime_doctor.py](controller/runtime_doctor.py)

Tests:

- [sandbox_tests/test_agentic_intent.py](sandbox_tests/test_agentic_intent.py)
- [sandbox_tests/test_agent_tools.py](sandbox_tests/test_agent_tools.py)
- [sandbox_tests/test_agentic_processor.py](sandbox_tests/test_agentic_processor.py)
- [sandbox_tests/test_tauri_backend_routes.py](sandbox_tests/test_tauri_backend_routes.py)
- [sandbox_tests/test_api_key_store.py](sandbox_tests/test_api_key_store.py)
- [sandbox_tests/test_github_adapter.py](sandbox_tests/test_github_adapter.py)
- [sandbox_tests/test_vps_deploy_adapter.py](sandbox_tests/test_vps_deploy_adapter.py)
- [sandbox_tests/test_ziel_policy.py](sandbox_tests/test_ziel_policy.py)
- [sandbox_tests/test_ouroboros_self_context.py](sandbox_tests/test_ouroboros_self_context.py)
- [sandbox_tests/test_ouroboros_status_contract.py](sandbox_tests/test_ouroboros_status_contract.py)
- [tests/test_docker_runner.py](tests/test_docker_runner.py)

Handoff:

- [HANDOFF_OUROBOROS_CHAT_CONNECTORS_VPS_ZIEL_2026-05-11.md](HANDOFF_OUROBOROS_CHAT_CONNECTORS_VPS_ZIEL_2026-05-11.md)

## Architecture boundaries

- Ordinary cockpit chat can classify and route agentic intents without bypassing existing approval and safety gates.
- Public internet and travel lookup support remains read-only and non-mutating.
- Gmail and Google Drive foundation is private-read gated. Mailbox and Drive contents require exact Akkoord before read attempts and never expose OAuth material.
- GitHub foundation is read-only by default. Public repository metadata/search can proceed without private approval; private metadata is blocked unless exact Akkoord is provided. Tokens are resolved through the API key store or environment but are never returned in payloads.
- VPS deployment foundation is preview-first. Login checks and sync previews are supported as safe plumbing, while sync execute requires exact Akkoord and keeps fixed remote target constraints and exclusion rules.
- Ziel policy is loaded as local runtime context and guardrail metadata only. It never bypasses ToolBridge, approval, no-secrets, external-call, or OODA/Hippocampus/DreamCycle boundaries.
- OODA, Hippocampus, and DreamCycle stay local-only. The prior boundary suite passed and no connector/deploy path is allowed to mutate those boundaries.

## Validation already completed before this handoff task

- Consolidated targeted suite: 119 tests OK, 38 skipped.
- OODA/Hippocampus/DreamCycle boundary suite: 11 tests OK.
- Compile validation over modified backend/test files: 32 files OK.
- No real SSH, rsync execute, Gmail, Google Drive, or GitHub network operations were run.

## Final validation during commit handoff

- `python3 -m pytest -q sandbox_tests/test_agentic_intent.py sandbox_tests/test_agent_tools.py sandbox_tests/test_agentic_processor.py sandbox_tests/test_tauri_backend_routes.py sandbox_tests/test_api_key_store.py sandbox_tests/test_github_adapter.py sandbox_tests/test_vps_deploy_adapter.py sandbox_tests/test_ziel_policy.py sandbox_tests/test_ouroboros_self_context.py sandbox_tests/test_ouroboros_status_contract.py tests/test_docker_runner.py` could not run because this environment has no `pytest` module installed for `python3`.
- `python3 -m py_compile` passed for the in-scope controller, script, sandbox test, and Docker runner test files.
- `git diff --check` passed for the same in-scope file set plus this handoff file.
- `git status --short --untracked-files=all` was inspected before staging; runtime/private/cache and unrelated dirty files remained excluded.

## Deployment and VPS notes

- Do not run real VPS sync or deploy from this handoff.
- VPS remote target remains constrained to /var/www/philip-wintrip.nl/html/Ouroboros/.
- Sync preview should use dry-run semantics and standard excludes for secrets, environment files, runtime state, uploads, Chroma state, and model/cache artifacts.
- Sync execute remains gated by exact Akkoord and should only be used in a dedicated deployment task after reviewing the dry-run preview.

## Files intentionally excluded from staging

Runtime/private/cache/state artifacts and uploads:

- [wintrip_brain/chroma.sqlite3](wintrip_brain/chroma.sqlite3)
- [wintrip_brain/](wintrip_brain)
- [data/uploads/](data/uploads)
- [unsloth_compiled_cache/moe_utils.py](unsloth_compiled_cache/moe_utils.py)
- .secrets
- .env files

Unrelated or out-of-scope dirty files observed during handoff inspection:

- [docker-compose.yml](docker-compose.yml)
- [ouroboros_cockpit/src/App.tsx](ouroboros_cockpit/src/App.tsx)
- [ouroboros_esoteric/ouroboros_consciousness_loop.py](ouroboros_esoteric/ouroboros_consciousness_loop.py)
- [controller/multi_api_router.py](controller/multi_api_router.py)
- [controller/unsloth_adapter.py](controller/unsloth_adapter.py)
- [controller/agent_runtime/adapters/ecosystem_cli.py](controller/agent_runtime/adapters/ecosystem_cli.py)
- [controller/subscription_store.py](controller/subscription_store.py)
- [sandbox_tests/test_multi_api_router.py](sandbox_tests/test_multi_api_router.py)
- [sandbox_tests/test_subscription_store.py](sandbox_tests/test_subscription_store.py)
- [sandbox_tests/test_ecosystem_cli.py](sandbox_tests/test_ecosystem_cli.py)
- [controller/camera_manager.py](controller/camera_manager.py)
- [scripts/generate_ouroboros_quantumveld.py](scripts/generate_ouroboros_quantumveld.py)
- [QuantumNode.txt](QuantumNode.txt)
- [camera-tools.sh](camera-tools.sh)
- [HANDOFF_OUROBOROS_OODA_DREAMCYCLE_HIPPOCAMPUS_2026-05-10.md](HANDOFF_OUROBOROS_OODA_DREAMCYCLE_HIPPOCAMPUS_2026-05-10.md)
- [.roo/skills/architect/SKILL.md](.roo/skills/architect/SKILL.md)
- [.roo/skills/coder/SKILL.md](.roo/skills/coder/SKILL.md)
- [.roo/skills/critic/SKILL.md](.roo/skills/critic/SKILL.md)
- [.roo/skills/foreman/SKILL.md](.roo/skills/foreman/SKILL.md)

## Next steps

1. Review the pushed branch and compare staged files against the in-scope list above.
2. If enabling real connector execution later, create separate adapter tasks with explicit approvals and mocked tests first.
3. For VPS deployment, run only a dry-run preview first, inspect excludes and target path, then request exact Akkoord for any mutating sync task.
4. Keep OODA, Hippocampus, DreamCycle, and Ziel policy as local guardrail/context layers unless a future architecture handoff explicitly changes those boundaries.
