# Restore Fase 1 Source Bundle

The full Fase 1 source tree is stored in `source_bundle.tar.gz.b64` on this branch because the local environment could not authenticate a normal `git push` (`gh` was missing from the configured credential helper).

To restore the exact source files from this branch:

```bash
cd /tmp
mkdir -p ouroboros_fase1_restore
cd ouroboros_fase1_restore
base64 -d /path/to/source_bundle.tar.gz.b64 > source_bundle.tar.gz
tar -xzf source_bundle.tar.gz
cd Fase_1
python -m unittest discover -s tests
./start-docker.sh
```

Expected verification from Gordon:

- Chroma Python client heartbeat succeeded.
- Collection available: `ouroboros_11d_hippocampus`.
- Gradio running on `0.0.0.0:7860`.
- Unit tests inside container: `10/10 PASSED`.
- LangGraph graph-check returned a compiled graph.

Local full source commit prepared by Codex:

```text
29d02cd Add Resonant Ouroboros Fase 1 stack
```

Normal `git push -u origin Fase_1` was attempted but blocked by:

```text
/usr/bin/gh auth git-credential get: line 1: /usr/bin/gh: No such file or directory
fatal: could not read Username for 'https://github.com': No such device or address
```
