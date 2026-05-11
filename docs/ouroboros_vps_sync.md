# Ouroboros VPS Sync

The VPS deploy adapter uses SSH metadata from environment variables or
`.secrets/vps.env`. It never reads or stores passwords, private keys, bearer
tokens, or browser session material. SSH authentication stays in `~/.ssh/config`
and the host `ssh-agent`.

## Setup

1. Copy `config/vps.env.example` to `.secrets/vps.env`.
2. Edit `.secrets/vps.env` with the SSH alias, user, and port.
3. Make sure the alias works from the host:

```bash
ssh wintrip-vps 'printf ouroboros-vps-ok'
```

If `ssh-copy-id` says `ERROR: No identities found`, create a local key first:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -C "pwintri2@wintripai-vps" -N ""
ssh-copy-id -i ~/.ssh/id_ed25519.pub philip@87.106.137.223
ssh -o BatchMode=yes philip@87.106.137.223 'printf ouroboros-vps-ok'
```

The second command asks once for the VPS password and installs only the public
key. Do not put VPS passwords in `.env`, `.secrets/vps.env`, memory, or code.

4. Start the host bridge:

```bash
python3 scripts/rclone_host_bridge.py --bind 0.0.0.0 --port 8766
```

The bridge and backend will load `.secrets/vps.env` automatically when the VPS
adapter starts.

## Safe Flow

In the Cockpit, open the `Context` tab. It now shows:

- `Local Backend`: context counted directly by the backend workspace.
- `Host / Bridge`: context counted through the host bridge.
- `VPS Sync`: deploy adapter status plus `Status`, `Login Check`,
  `Dry-run Sync`, and `Execute Sync` actions.
- `VPS UI Artifact Sync`: deploys the built React cockpit from
  `ouroboros_cockpit/dist/` to the fixed VPS webroot. The execute action builds
  the UI first and then rsyncs the artifact directory.
- `Chroma Merge`: checks local/VPS Chroma, previews missing records in each
  direction, and then performs a bidirectional merge only after exact `Akkoord`.

Use status and login checks first:

```bash
python3 - <<'PY'
from controller.vps_deploy_adapter import VPSDeployAdapter
print(VPSDeployAdapter().status())
print(VPSDeployAdapter().login_check())
PY
```

Then run a dry-run preview. Real sync execution requires exact `Akkoord`.

The remote target is fixed in code:

```text
/var/www/philip-wintrip.nl/html/Ouroboros/
```

Secrets, `.env` files, `.secrets`, SSH material, Chroma state, uploads, caches,
model artifacts, and large model files are excluded from rsync by default.

## UI Artifact Sync

The general workspace sync intentionally excludes `dist/` and `build/`
directories. That keeps generated artifacts out of broad deploys, but a public
webroot needs the built Cockpit artifact.

Use the dedicated UI actions instead:

1. `UI Dry-run` previews `ouroboros_cockpit/dist/` to the fixed VPS webroot.
2. `UI Execute` requires exact `Akkoord`, runs `npm --prefix ouroboros_cockpit
   run build`, then rsyncs the fresh `dist/` contents.

The VPS route serves the cockpit under `/Ouroboros/`, not the domain root. The
UI execute path therefore builds with:

```env
VITE_PUBLIC_BASE=/Ouroboros/
VITE_BACKEND_URL=/Ouroboros
TAURI_BACKEND_URL=/Ouroboros
```

Override these only when the public route changes:

```env
WINTRIP_VPS_UI_PUBLIC_BASE=/Ouroboros/
WINTRIP_VPS_UI_BACKEND_URL=/Ouroboros
```

`UI Execute` also refreshes `ouroboros_cockpit/dist/Cockpit.html` as an exact
copy of `dist/index.html` before rsync. That keeps the existing VPS URL
`/Ouroboros/Cockpit.html` on the same Cockpit app, with the same menus and
buttons as the root `/Ouroboros/` entrypoint.

If npm lives outside `PATH`, set this non-secret key in `.secrets/vps.env`:

```env
WINTRIP_NPM_BIN=/home/pwintri2/.nvm/versions/node/v22.22.2/bin/npm
```

The UI artifact prefers `rsync`. If the host has `ssh` and `scp` but no
`rsync`, `UI Dry-run` falls back to a file manifest and `UI Execute` uploads
the built files one by one with `scp`, excluding source maps.

## Chroma Merge

Do not copy `wintrip_brain/chroma.sqlite3` directly while either runtime is
active. The merge adapter uses Chroma's collection API instead:

- local records are exported through the local Chroma client;
- VPS records are exported over SSH on the VPS;
- missing records are imported on both sides;
- tool output returns counts and metadata only, never raw documents.

Add these non-secret VPS-side path hints when the defaults are wrong:

```env
WINTRIP_VPS_REMOTE_WORKSPACE=/var/www/philip-wintrip.nl/html/Ouroboros
WINTRIP_VPS_REMOTE_CHROMA_PATH=/var/www/philip-wintrip.nl/html/Ouroboros/wintrip_brain
WINTRIP_VPS_REMOTE_CHROMA_HTTP_URL=
WINTRIP_CHROMA_SYNC_COLLECTIONS=wintrip_knowledge,wintrip_training_11d,wintrip_world_understanding,wintrip_ooda_dreamcycle_11d,wintrip_trigger_actions_11d,wintrip_agentic_sessions_11d
```

If the VPS Chroma service is HTTP-only on the VPS host, use for example:

```env
WINTRIP_VPS_REMOTE_CHROMA_HTTP_URL=http://127.0.0.1:18000
```

Recommended order:

1. `Chroma Status`
2. `Chroma Preview`
3. review `missing_on_local` and `missing_on_remote`
4. `Chroma Merge` with exact `Akkoord`

## Roo / DeepSeek Roots

The backend resolves neighbouring agent roots dynamically. On the laptop it
prefers `/home/pwintri2/Roo-code` and `/home/pwintri2/deepseek`; on the VPS it
prefers the mounted webroot copies:

```text
/workspace/Roo
/workspace/deepseek
```

This makes Roo and DeepSeek visible in `/api/fase8/external-capabilities`.
DeepSeek source reading/searching works from slash commands such as
`/deepseek list docs`, `/deepseek read README.md`, and
`/deepseek search docs pattern`. Running the DeepSeek CLI itself still requires
a launchable Node/Cargo/binary runtime on the VPS.

## Roo Cloud Login From The VPS

Roo Cloud auth belongs to the laptop/browser Roo CLI, not to the public VPS
container. The VPS Cockpit can still use it through a reverse SSH tunnel:

```bash
scripts/start_roo_vps_bridge_tunnel.sh
```

That exposes the laptop host bridge to the VPS backend on port `18766`. The VPS
Roo adapter auto-detects this URL and routes Roo Cloud login/model catalog calls
through the laptop bridge. The tunnel PID is stored in:

```text
.secrets/ouroboros_roo_bridge_tunnel.pid
```

## Peer Core Pulse

While the laptop is on, start the sanitized laptop<->VPS core pulse with:

```bash
python3 scripts/ouroboros_peer_exchange.py --approval Akkoord --loop --interval 60
```

The current detached loop writes to `.secrets/ouroboros_peer_exchange.log` and
stores its PID in `.secrets/ouroboros_peer_exchange.pid`. Stop it with:

```bash
kill "$(cat .secrets/ouroboros_peer_exchange.pid)"
```
