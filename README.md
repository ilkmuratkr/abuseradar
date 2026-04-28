# AbuseRadar

Independent breach intelligence for the compromised institutional web. AbuseRadar exposes silent compromises in government, university and other institutional websites — leaked admin panels, web shells, exfiltrated documents, hijacked subdomains and the criminal SEO injections layered on top of them — then automates evidence collection, multi-channel notification and coordinated takedown across hosting providers, registrars and CERT teams.

> Operates from Istanbul · Reports globally · Not a commercial product

## What's in here

```
seospamwatch/
├── app/                        FastAPI backend + crawler + classifier + notifier + complainant
├── web/                        Marketing site (abuseradar.org) + new HTML/JS console
│   ├── index.html              Landing page (5 languages)
│   ├── research.html           Research / publications
│   ├── login.html              Console gateway
│   ├── privacy.html            Legal
│   ├── locales/                en · tr · pt · es · fr i18n dictionaries
│   ├── img/generated/          Gemini-generated visuals
│   └── console/                Modern HTML/JS operations console (light + dark mode)
├── db/init.sql                 Postgres schema
├── vpn/                        WireGuard configs (TR + US egress)
├── infra/                      nginx, Caddy, systemd unit
├── data/                       Runtime: CSV inbox, evidence vault (gitignored)
├── docker-compose.yml          Base stack (8 services)
├── docker-compose.prod.yml     Production overlay (127.0.0.1 binds, no source mounts)
├── Makefile                    Common commands
├── .env.example                Environment template
└── DEPLOY.md                   Ubuntu production deployment guide
```

## Quick start (local dev — Mac or Linux)

Prerequisites: Docker Desktop (Mac) or Docker Engine + Compose plugin (Linux), GNU make, a Gemini API key, two WireGuard configs (TR + US egress).

```bash
# 1. Clone
git clone git@github.com:<you>/abuseradar.git
cd abuseradar

# 2. Environment + secrets
make init                        # copies .env.example → .env
$EDITOR .env                     # set GEMINI_API_KEY, POSTGRES_PASSWORD, RESEND_API_KEY

# 3. WireGuard configs (gitignored)
cp vpn/tr/wg0.conf.example vpn/tr/wg0.conf
cp vpn/us/wg0.conf.example vpn/us/wg0.conf
$EDITOR vpn/tr/wg0.conf vpn/us/wg0.conf   # paste your provider configs

# 4. Bring it up
make up                          # docker compose up -d
make vpn-check                   # confirm both VPN egresses work

# 5. Open
# Marketing site:  cd web && python3 -m http.server 8765   →  http://localhost:8765
# Console:         http://localhost:8765/console/   (production'da basic auth)
# FastAPI docs:    http://localhost:7777/docs
```

The website is fully static — no build step. You can serve `web/` with any static server (`python3 -m http.server`, `npx serve`, nginx, Cloudflare Pages, GitHub Pages).

## Common commands

```bash
make up               # Start all services
make down             # Stop all services
make logs             # Tail all logs
make logs-app         # Tail just the backend
make vpn-check        # Show egress IPs for both VPNs
make stats            # API stats
make pipeline         # Trigger one full pipeline run
make db-shell         # psql into the Postgres
make help             # Full command list
```

## Production deployment (Ubuntu)

The repo ships a single-file installer/manager: [`deploy.sh`](deploy.sh).

```bash
# On a fresh Ubuntu 22.04 / 24.04 box, as root:
curl -fsSL https://raw.githubusercontent.com/ilkmuratkr/abuseradar/main/deploy.sh -o /tmp/deploy.sh
chmod +x /tmp/deploy.sh
sudo /tmp/deploy.sh --init --domain abuseradar.org --email hello@abuseradar.org
# → installs Docker, ufw, nginx, clones repo to /opt/abuseradar, drops .env / vpn templates

# Edit secrets the installer warned about
sudo $EDITOR /opt/abuseradar/.env
sudo $EDITOR /opt/abuseradar/vpn/tr/wg0.conf
sudo $EDITOR /opt/abuseradar/vpn/us/wg0.conf

# Bring it up + issue SSL
cd /opt/abuseradar
sudo ./deploy.sh --check                # preflight: env, vpn, disk, ports
sudo ./deploy.sh --start
sudo ./deploy.sh --ssl                  # Let's Encrypt via certbot --nginx
sudo ./deploy.sh --status
```

Day-to-day:

```bash
sudo ./deploy.sh --update           # git pull + rebuild + restart
sudo ./deploy.sh --restart          # just restart
sudo ./deploy.sh --logs app         # tail one service
sudo ./deploy.sh --backup           # pg_dump → /var/backups/abuseradar/
sudo ./deploy.sh --help             # full action list
```

See [DEPLOY.md](DEPLOY.md) for the manual step-by-step (Docker install, env hardening, nginx + Let's Encrypt, systemd auto-start, backups, troubleshooting, Mac↔Ubuntu differences).

## Architecture

Eight Docker services on an `internal` bridge network:

- **vpn-tr** + **vpn-us** — WireGuard egress (Istanbul, Washington) with a microSOCKS proxy on `:1080`. All outbound traffic from `app`, `crawler`, `openclaw` flows through one of these.
- **db** — Postgres 16
- **redis** — Redis 7
- **app** — FastAPI backend on `:8000` (mapped to host `:7777` in dev, `127.0.0.1:7777` in prod). Exits via VPN-US.
- **crawler** — Playwright + Chromium worker. Renders suspect pages via VPN-TR with cloaking-aware probes.
- **web** — nginx static container serving the marketing site + admin console (`/console/`). nginx host layer adds basic auth for `/console/` and `/api/`.
- **openclaw** — autonomous AI agent on `:18789`, files abuse complaints with hosting providers, registrars, Cloudflare Safe Browsing, etc. Exits via VPN-US.

The web console at `web/console/` is a static SPA-ish multi-page app (no build step) that talks to the FastAPI backend over `/api/*` (in production, nginx reverse-proxies that path to `app:8000`).

## Security

- `.env`, `vpn/**/wg0.conf`, `data/evidence/`, `data/csv/processing/` are all **gitignored**. Never commit secrets.
- Production: only `:80` and `:443` (nginx) face the public internet. All Docker ports bind to `127.0.0.1` only.
- The admin console at `/console/` and the API at `/api/` are protected by nginx basic auth (`/etc/nginx/.abuseradar.htpasswd`). Public marketing pages remain open.
- Postgres password is required (no insecure default) — `POSTGRES_PASSWORD` must be set in `.env`.

## License

TBD.
