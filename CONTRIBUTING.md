# Contributing to Ouroboros

Thanks for helping improve Ouroboros — a local-first private AI agent for macOS.

## Good first contributions

- Improve install instructions or troubleshooting notes.
- Add tests around FastAPI endpoints and controller utilities.
- Polish the Ambient Sentinel demo dashboard.
- Document local-first/privacy safeguards.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r controller/requirements.txt
pip install pytest flake8
```

## Checks

```bash
flake8 controller/ --count --select=E9,F63,F7,F82 --show-source --statistics
pytest test_phase1.py test_phase2.py test_phase3.py test_phase4.py --tb=short -q
```

Some sandbox tests require Docker Desktop to be running.

## Pull requests

- Keep changes focused and local-first by default.
- Do not commit secrets, private data, model keys, or local database files.
- Update `README.md` or `SESSION.md` when behavior or setup changes.
