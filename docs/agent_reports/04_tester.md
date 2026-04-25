# 04 Tester

## Test Strategy

Because Docker execution requires explicit user permission, the immediate test
suite is stdlib-only and runs without installing host dependencies.

Local command:

```bash
python -m unittest discover -s tests
```

Docker command prepared but not executed:

```bash
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 up --build -d
```

## Coverage

- Hertz base wave stays in 418-432 Hz.
- Random creative spikes reach 600-1200 Hz.
- Low/high frequency behavior mapping changes curiosity and browsing style.
- 11D schema produces exactly 11 numeric vector dimensions.
- Required 11D metadata plus vibration fields are present.
- Seed parser loads exact `AGI Kennis.txt` topics.
- URL safety blocks localhost and file URLs.
- Dry-run PAEU seed queue stores 11D records.
- Gordon progress file bridge writes progress.

## Results

- `python3 -m unittest discover -s tests`
  - Result: `Ran 10 tests in 0.001s`
  - Status: `OK`
- `python3 -m compileall -q resonant_ouroboros tests`
  - Status: `compileall OK`
- `python3 -m resonant_ouroboros.main learn-seed --seed 'AGI Kennis.txt' --max-topics 2 --dry-run`
  - Result: queued 2 seed topics without browser.
  - Gordon progress file was written.
- `./start-docker.sh`
  - Result in Codex shell: exits `127` with `docker is not available in this terminal.`
  - This verifies the launcher guard; Docker execution still belongs to Gordon
    or another Docker-enabled terminal.

## Docker Attempt After Permission

The user granted explicit permission to run Docker Compose and use ChromaDB in
Docker. Codex attempted:

```bash
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 up --build -d
```

Result:

```text
/bin/sh: line 1: docker: command not found
```

Follow-up checks found no `docker`, `docker-compose`, `podman`, or
`/var/run/docker.sock` available in this Codex execution environment. The
prepared command should be run by Gordon or another terminal with Docker access:

```bash
cd /tmp/codex-workspace
./start-docker.sh
```

## Chroma Client Fix Prepared

After Gordon verified Chroma heartbeat but reported Python client connection
failure, a fix archive was prepared:

- `/home/pwintri2/Ouroboros1_1/ouroboros_chroma_fix.tar.gz`
- `/home/pwintri2/Ouroboros1_1/CHROMA_FIX_FOR_GORDON.md`

The fix pins the Python Chroma client to `0.5.23`, matching the server image,
adds explicit client settings/tenant/database, retries `HttpClient` creation,
adds a Chroma healthcheck, and uses `/workspace/agi_kennis.txt` consistently.

## Gordon Docker Verification Passed

Gordon reported the full Docker stack operational:

- Chroma Python client heartbeat succeeded.
- Collection available: `ouroboros_11d_hippocampus`.
- Gradio running on `0.0.0.0:7860`.
- Unit tests inside container: `10/10 PASSED`.
- LangGraph graph-check returned a compiled graph.
- Containers are running after clean rebuild and startup.

## Live Collection Verification

Codex reached the live services over exposed ports and verified:

- Gradio responds with HTTP `200` on port `7860`.
- Chroma heartbeat responds on port `8001`.
- Collection `ouroboros_11d_hippocampus` exists with dimension `11`.
- Collection count: `42`.
- Sampled records: `42/42` have all required 11D metadata plus
  `current_hz` and `vibration_mood`.
- Sampled embeddings: `42/42` are exactly 11-dimensional.
- Browser snapshot documents: `42/42`.
- Unique seed topics represented: `17`.
- Hertz range observed in records: `418.026` to `1086.406`.
- Vibration moods observed: `creative_spike`, `curious_scan`, `deep_read`.

Quality finding: `26/42` sampled documents were DuckDuckGo bot-challenge pages.
Future seed browsing has been adjusted to start from Wikipedia search by
default via `HUMAN_SEARCH_BASE_URL`.
