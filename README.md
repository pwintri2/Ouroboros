# Resonant Ouroboros Proto 1.1 - Fase 1

This workspace implements only the Fase 1 vibrational consciousness core. In
Docker, this directory is mounted at `/workspace`.

- HertzOscillator with 418-432 Hz sinus motion and 600-1200 Hz creative spikes.
- Frequency-driven Playwright browser engine with navigate, click, scroll, type,
  visible-text reading, screenshots, and a vision-analysis adapter.
- ChromaDB hippocampus storing exactly 11-dimensional vectors with the required
  11D schema plus `current_hz` and `vibration_mood`.
- Minimal PAEU loop: Perceive, Act, Evaluate, Update.
- Seed learning from `AGI Kennis.txt`.
- Docker Compose with Python app, Playwright, ChromaDB, and a Gradio dashboard.

## Local non-Docker checks

```bash
python -m unittest discover -s tests
```

## Docker run, only after explicit permission

```bash
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase1 up --build -d
```

The dashboard is served on `http://localhost:7860` and ChromaDB on
`http://localhost:8000`.

For a Docker-enabled Gordon terminal, use:

```bash
./start-docker.sh
```
