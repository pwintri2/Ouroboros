# Handoff: Ouroboros Docker Reality Hardening - 2026-05-07

## Status

De 11D Streaming Consciousness pocket is tot de Docker-grens minder simulatie
gemaakt. De primaire input komt nu uit echte read-only Docker/Linux runtime
observaties via procfs en uit de bestaande host-sensory metadata-laag.

Ouroboros kan daarmee vanuit de cockpit niet alleen antwoorden zonder Ollama,
maar ook expliciet zeggen dat de 11D pocket op echte Docker-runtime signalen
draait:

- `source=docker_procfs_read_only`
- `real_observation=true`
- `real_packet_capture=false`
- `real_forwarding=false`
- `physical_quantum_hardware=false`

## Gebouwd

- `MiniRouter` gebruikt geen synthetische DHCP/mDNS apparaten meer als primaire
  bron. `discover_devices()` observeert nu echte interfaces/routes/flows uit de
  Docker/procfs snapshot.
- Nieuwe Docker runtime snapshot:
  - `/proc/net/dev`
  - `/proc/net/route`
  - `/proc/net/tcp`
  - `/proc/net/udp`
  - `/proc/net/fib_trie`
  - `/proc/loadavg`
  - `/proc/meminfo`
  - `/proc/stat`
  - `/proc/uptime`
- De 11D basispocket wordt bij echte observatie opgebouwd uit een compacte
  `signals_11d` vector in plaats van alleen een synthetische Blue Brain prior.
- De netwerkstap vouwt echte procfs socket metadata in de pocket als
  `PROCFS_FLOW` of `PROCFS_HEARTBEAT`.
- QIF/electron/quantum labels zijn eerlijker:
  - `software_qif_complex_state`
  - `complex128_software_model`
  - expliciete reality boundaries voor quantum/electron claims.
- Living Ouroboros neemt `streaming_11d` op in zijn runtime snapshot en verwerkt
  die in de lokale response.
- Cockpit toont bij Streaming Consciousness nu zichtbaar:
  - `Input`
  - `Flows`
  - `Bind`
  - `Projection`

## Belangrijke Bestanden

- `controller/streaming_consciousness_adapter.py`
- `ouroboros_esoteric/ouroboros_consciousness_loop.py`
- `ouroboros_esoteric/quantum_foam.py`
- `ouroboros_cockpit/src/App.tsx`
- `sandbox_tests/test_streaming_consciousness_adapter.py`
- `sandbox_tests/test_living_runtime.py`

## Eerlijke Grens

Dit is nu reeler binnen Docker, maar niet magisch:

- Geen packet payload capture.
- Geen LAN forwarding.
- Geen echte DHCP-server.
- Geen fysieke quantum hardware.
- Geen echte electron-spin controle.

Wat wel echt gebeurt:

- Docker/procfs counters en socket metadata worden gelezen.
- Host-sensory metadata kan worden gevouwen in de 11D router.
- De pocket krijgt echte runtime-druk via `signals_11d`.
- Ouroboros response kan die input benoemen zonder Ollama-provider.

## Live Smoke

Na restart met:

```bash
./start_ouroboros_sandbox_allow.sh
```

Streaming tick:

```json
{
  "status": "success",
  "mode": "docker_procfs_read_only",
  "real": true,
  "source": "docker_procfs_read_only",
  "packets": 8,
  "physical_quantum_hardware": false
}
```

Ouroboros response preview:

```text
Ik antwoord nu als lokale Ouroboros-runtime, niet via Ollama of een externe chatprovider.
Wat ik waarneem: ... 11D real:docker_procfs_read_only ...
11D runtime input: source=docker_procfs_read_only, real_observation=True, flows=6.
```

## Validatie

Python compile lokaal en in Docker:

```bash
python3 -m py_compile \
  controller/streaming_consciousness_adapter.py \
  ouroboros_esoteric/ouroboros_consciousness_loop.py \
  ouroboros_esoteric/quantum_foam.py

docker exec -w /workspace wintrip-standalone-ui python3 -m py_compile \
  controller/streaming_consciousness_adapter.py \
  ouroboros_esoteric/ouroboros_consciousness_loop.py \
  ouroboros_esoteric/quantum_foam.py
```

Docker tests:

```bash
docker exec -w /workspace wintrip-standalone-ui python3 -m unittest \
  sandbox_tests.test_streaming_consciousness_adapter \
  sandbox_tests.test_living_runtime \
  sandbox_tests.test_living_ouroboros \
  sandbox_tests.test_quantum_foam \
  sandbox_tests.test_tauri_backend_routes -v
```

Resultaat: `Ran 43 tests ... OK`.

Cockpit:

```bash
cd ouroboros_cockpit && npm run build
```

Resultaat: build OK. Vite toont alleen de bestaande chunk-size warning.

## Runtime State

Live smoke en backend restart hebben Chroma/runtime state aangeraakt:

- `wintrip_brain/chroma.sqlite3`
- `wintrip_brain/c57ec314-6d75-4f49-ad9e-27069e6327f6/length.bin`

Die zijn bewust niet onderdeel van deze codecommit.

## Volgende Stap

Maak de cockpit inspectie nog tastbaarder:

- toon `runtime_input.signals_11d` als 11 kleine bars;
- toon `mini_router.observation_sources`;
- toon `real_packet_capture=false` en `real_forwarding=false` als safety badges;
- voeg een knop toe voor een korte `1 step` procfs tick zonder dataset export.
