# RecruiterAI — Production Deployment Runbook

Verified during the deployment of `e4a137d` on 2026-10-03. Only commands/paths
actually used or confirmed on the live server are recorded here. **Never put
secrets, private keys, passwords, tokens or API keys in this file.**

> Future Claude sessions: read this file first. Do NOT ask the user how to deploy
> unless a step here is proven invalid or an external credential/approval is
> genuinely required.

## Host & access
- **Provider / OS:** Oracle Cloud Infrastructure (OCI) compute, **Oracle Linux Server 9.8**. Small shape (~945 MB RAM).
- **Public IP:** `140.245.235.18`  ·  **Public site:** `https://hire.dayzero.partners`
- **SSH user:** `opc` (Oracle Linux default). *Not* `ubuntu`/`oracle`/`root` (all rejected).
- **SSH key:** the **OCI-generated keypair**, locally at `~/Downloads/ssh-key-2026-09-14.key` (filename is `ssh-key-<date>.key`). NOTE: `~/.ssh/id_ed25519` is **not** the server key (it fails auth, and isn't the GitHub key either). `known_hosts` has the host but doesn't record which local key authenticated — use the OCI `.key` file.
- **Connect:** `ssh -i ~/Downloads/ssh-key-2026-09-14.key opc@140.245.235.18`

## Application layout (on server)
- **App root (NOT a git repo):** `/opt/recruiterai` — code is **built locally and copied here**, never `git pull`ed on the server (there is no `.git` and **no Node/npm** on the box).
- **Backend:** systemd unit `recruiterai-backend.service` — `User=opc`, `WorkingDirectory=/opt/recruiterai`, venv `/opt/recruiterai/.venv`, `ExecStart=/opt/recruiterai/.venv/bin/uvicorn backend.api:app --host 127.0.0.1 --port 8000`, `EnvironmentFile=/etc/recruiterai.env`, `MemoryMax=500M`.
- **Frontend:** static SPA served by **nginx** from `/opt/recruiterai/frontend/dist` (`try_files $uri $uri/ /index.html`). nginx also reverse-proxies the API: `proxy_pass http://127.0.0.1:8000`. TLS via Certbot (`:443`), `server_name hire.dayzero.partners`.
- **Env/secrets:** `/etc/recruiterai.env` (OpenAI / CrustData / Harvest / Google OAuth keys). Not in the repo.
- **Deployed-SHA marker:** `/opt/recruiterai/DEPLOYED_SHA` (written by the deploy; see below).

## Production branch & verifying the deployed SHA
- **Branch:** `main` of `github.com/harshatummalapalli/RecruiterAI`.
- **Check what's live:** `ssh … opc@140.245.235.18 'cat /opt/recruiterai/DEPLOYED_SHA'`
  (older builds predating 2026-10-03 may have no marker.)

## Environment / feature flags (deployment-relevant)
- `SEARCH_COMPILER_SHADOW_ENABLED` — **must be unset or `false`** (default off). The Hiring-Intent Compiler runs in **shadow only**: with the flag off it does not execute and never touches retrieval. Verified unset in `/etc/recruiterai.env` for the `e4a137d` deploy.
- To enable shadow later (deliberate): add `SEARCH_COMPILER_SHADOW_ENABLED=true` to `/etc/recruiterai.env` and `sudo systemctl restart recruiterai-backend`. Shadow logs land in `/opt/recruiterai/output/compiler_shadow/` (gitignored). Compiled retrieval is still NOT wired to CrustData.
- No new Python deps for the compiler release; venv already has `pydantic 2.13.4` + `openai`. If `requirements.txt` changes: `/opt/recruiterai/.venv/bin/pip install -r /opt/recruiterai/requirements.txt`.

## Pre-deployment checks (local)
1. On `main` at the intended SHA, clean tree: `git rev-parse HEAD`, `git status --short`.
2. Target SHA is pushed to `origin/main`.
3. Node/npm available locally (server has none): `node --version`, `npm --version`.

## Deployment sequence (verified for `e4a137d`)
Run from the repo root on the local machine (`opc` user, OCI key):
```bash
# 1) Build the frontend locally (server has no Node)
cd frontend && npm install && npm run build && cd ..     # -> frontend/dist

# 2) Package backend + prompts + built frontend (exclude experiments/tests/venv/caches)
TB=/tmp/deploy.tgz
tar czf "$TB" --exclude='backend/experiments' --exclude='__pycache__' --exclude='*.pyc' \
    backend prompts frontend/dist requirements.txt

# 3) Copy to the server
scp -i ~/Downloads/ssh-key-2026-09-14.key "$TB" opc@140.245.235.18:/tmp/deploy.tgz

# 4) On the server: backup, clean-replace dist, extract, mark SHA, restart
ssh -i ~/Downloads/ssh-key-2026-09-14.key opc@140.245.235.18 'set -e
  TS=$(date +%Y%m%d-%H%M%S); sudo mkdir -p /opt/recruiterai/backups
  sudo tar czf /opt/recruiterai/backups/pre-<SHA>-$TS.tar.gz -C /opt/recruiterai backend prompts frontend/dist requirements.txt
  sudo rm -rf /opt/recruiterai/frontend/dist
  sudo tar xzf /tmp/deploy.tgz -C /opt/recruiterai
  sudo chown -R opc:opc /opt/recruiterai/backend /opt/recruiterai/prompts /opt/recruiterai/frontend /opt/recruiterai/requirements.txt
  echo "<SHA>" | sudo tee /opt/recruiterai/DEPLOYED_SHA >/dev/null
  sudo systemctl restart recruiterai-backend
  systemctl is-active recruiterai-backend'
```
nginx needs no reload for static `dist` updates. `backend/experiments/` and `tests/` are intentionally excluded from the server.

## Post-deployment smoke test (verified commands)
```bash
ssh -i ~/Downloads/ssh-key-2026-09-14.key opc@140.245.235.18 '
  systemctl is-active recruiterai-backend
  curl -s -o /dev/null -w "health %{http_code}\n" http://127.0.0.1:8000/health          # expect 200
  curl -s -o /dev/null -w "search %{http_code}\n" -X POST http://127.0.0.1:8000/search -d "{}"  # expect 401 (auth-gated)
  sudo journalctl -u recruiterai-backend --since "2 min ago" | grep -iE "error|traceback|SHADOW" | tail  # expect empty
  cat /opt/recruiterai/DEPLOYED_SHA'
curl -s -o /dev/null -w "site %{http_code}\n" https://hire.dayzero.partners/            # expect 200
```
Also confirm the served bundle matches the fresh build: the hashed JS name in
`/opt/recruiterai/frontend/dist/index.html` equals the `dist/assets/index-*.js` from the local build.
**Cannot be done headlessly:** a full authenticated recruiter search that returns
candidates (requires Google-OAuth login and spends CrustData credits) — verify in
the browser at `https://hire.dayzero.partners` after deploy.

## Rollback (previous build)
Each deploy writes a backup to `/opt/recruiterai/backups/pre-<SHA>-<timestamp>.tar.gz`
(verified created for `e4a137d`: `pre-e4a137d-20261003-122727.tar.gz`). To roll back:
```bash
ssh -i ~/Downloads/ssh-key-2026-09-14.key opc@140.245.235.18 '
  sudo rm -rf /opt/recruiterai/frontend/dist
  sudo tar xzf /opt/recruiterai/backups/pre-<SHA>-<timestamp>.tar.gz -C /opt/recruiterai
  sudo systemctl restart recruiterai-backend
  systemctl is-active recruiterai-backend'
```

## SSH "banner exchange" timeout — diagnosis (encountered before this deploy)
Symptom: `Test-NetConnection … -Port 22` succeeds (TCP open) but SSH hangs with
"Connection timed out during banner exchange." That is **server-side `sshd` unable
to complete the handshake** — not network/firewall (TCP ok) and not auth (banner
precedes auth). On this small box (945 MB; backend `MemoryMax=500M`) the usual cause
is **resource exhaustion** (OOM/CPU) or a **full disk**. Diagnose/fix without SSH:
- **OCI Console → Compute → the instance → "Run command"** (Oracle Cloud Agent; enable the "Compute Instance Run Command" plugin if needed) and run:
  `free -m; df -h; systemctl status sshd; dmesg -T | grep -i -E "killed process|out of memory" | tail`
- If starved: stop the offending process / free disk, then `sudo systemctl restart sshd`. **Do not reboot blindly; do not reset credentials.**
- The OCI serial/VNC **console asks for an OS password**, which these key-only images don't set — it's a dead end without first provisioning one; prefer Run Command.
By the time SSH access was granted for the `e4a137d` deploy the instance had recovered (≈447 MB free, disk 33%), so SSH connected normally and the banner timeout did not recur.
