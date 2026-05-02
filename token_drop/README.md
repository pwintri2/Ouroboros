# Ouroboros Token Drop

Gooi hier je tokenbestanden in en run:

```bash
./scripts/token_eater.py --scan
./start_ouroboros_sandbox_allow.sh
```

Bestandsnamen die automatisch herkend worden:
- Google: `google_token.json`, `gmail_token.json`, `drive_token.json`, `gcp_token.json`
- Microsoft: `microsoft_token.json`, `graph_token.json`, `azure_token.json`, `entra_token.json`

Het script print nooit tokenwaarden. Na import worden bronbestanden verplaatst naar
`.secrets/token_eater_imported/`.
