# Security Policy

Ouroboros is designed around local-first AI, explicit privacy boundaries, and sandboxed execution.

## Reporting vulnerabilities

Please open a private security advisory on GitHub or contact the maintainer through the repository owner profile. Do not publish exploit details in a public issue before a fix is available.

## Security expectations

- Sensitive data should remain local unless the user explicitly enables a cloud tier.
- IMAP integrations must remain read-only.
- Generated code must run in the Docker sandbox, not directly on the host.
- Do not commit `.env` files, API keys, local ChromaDB stores, email exports, or personal documents.

## Supported scope

Security fixes are currently prioritized for the Python FastAPI controller, Ambient Sentinel demo, sandbox executor, and local data-ingestion paths.
