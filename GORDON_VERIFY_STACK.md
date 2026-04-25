# Gordon Verification: Ouroboros Stack

Gordon appears to have started the generic `codex-workspace` container. That is
not the required Fase 1 stack. The required stack has two services:

- `chroma`
- `ouroboros`

Run these commands from a Docker-enabled terminal on the host:

```bash
cd /tmp/codex-workspace

ls -la
test -f Dockerfile
test -f docker-compose.ouroboros.yml
test -f "AGI Kennis.txt"
test -d resonant_ouroboros

docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 up --build -d

docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 ps
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 logs --tail=120 chroma
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 logs --tail=160 ouroboros

curl -fsS http://localhost:8000/api/v1/heartbeat || curl -fsS http://localhost:8000/api/v2/heartbeat
curl -I http://localhost:7860

docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 exec ouroboros python -m unittest discover -s tests
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 exec ouroboros python -m resonant_ouroboros.main graph-check

docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 exec ouroboros sh -lc 'test -f /workspace/AGI\ Kennis.txt && echo "seed file OK"'
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 exec ouroboros sh -lc 'tail -n 40 /workspace/gordon_progress.log || true'
```

Report back:

1. `ps` output showing `chroma` and `ouroboros`.
2. Chroma heartbeat result.
3. Gradio response on port 7860.
4. Unit test result inside `ouroboros`.
5. LangGraph graph-check result.
6. Any errors from `chroma` or `ouroboros` logs.
7. Whether `/workspace/AGI Kennis.txt` and `/workspace/gordon_progress.log` exist.
