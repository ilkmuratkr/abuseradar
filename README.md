# AbuseRadar

Independent breach intelligence for the compromised institutional web. AbuseRadar exposes silent compromises in government, university and other institutional websites — leaked admin panels, web shells, exfiltrated documents, hijacked subdomains and the criminal SEO injections layered on top of them — then automates evidence collection, multi-channel notification and coordinated takedown across hosting providers, registrars and CERT teams.

> Operates from Istanbul · Reports globally · Not a commercial product

## What's in here

```
seospamwatch/
├── app/                        FastAPI backend + crawler + classifier + notifier + complainant
├── dashboard/                  Streamlit operations dashboard (legacy admin)
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
# Console:         http://localhost:8765/console/
# FastAPI docs:    http://localhost:7777/docs
# Streamlit:       http://localhost:7778
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

See [DEPLOY.md](DEPLOY.md) for the full server setup (Docker install, env hardening, nginx + Let's Encrypt, systemd auto-start, backups).

Short version:

```bash
# On a fresh Ubuntu 22.04 / 24.04 box
git clone git@github.com:<you>/abuseradar.git /opt/abuseradar
cd /opt/abuseradar
cp .env.example .env && $EDITOR .env       # set APP_ENV=production, strong POSTGRES_PASSWORD
cp vpn/tr/wg0.conf.example vpn/tr/wg0.conf && $EDITOR vpn/tr/wg0.conf
cp vpn/us/wg0.conf.example vpn/us/wg0.conf && $EDITOR vpn/us/wg0.conf

# Use the prod overlay (127.0.0.1 binds, restart=always, --workers 4)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# nginx + SSL  (or use Caddy — see infra/Caddyfile)
sudo cp infra/nginx/abuseradar.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/abuseradar.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d abuseradar.org -d www.abuseradar.org
sudo systemctl reload nginx

# Boot-time auto-start
sudo cp infra/systemd/abuseradar.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now abuseradar.service
```

## Architecture

Eight Docker services on an `internal` bridge network:

- **vpn-tr** + **vpn-us** — WireGuard egress (Istanbul, Washington) with a microSOCKS proxy on `:1080`. All outbound traffic from `app`, `crawler`, `openclaw` flows through one of these.
- **db** — Postgres 16
- **redis** — Redis 7
- **app** — FastAPI backend on `:8000` (mapped to host `:7777` in dev, `127.0.0.1:7777` in prod). Exits via VPN-US.
- **crawler** — Playwright + Chromium worker. Renders suspect pages via VPN-TR with cloaking-aware probes.
- **dashboard** — Streamlit on `:8501` (host `:7778` / `127.0.0.1:7778` in prod). Legacy admin — being replaced by the static HTML/JS console under `web/console/`.
- **openclaw** — autonomous AI agent on `:18789`, files abuse complaints with hosting providers, registrars, Cloudflare Safe Browsing, etc. Exits via VPN-US.

The web console at `web/console/` is a static SPA-ish multi-page app (no build step) that talks to the FastAPI backend over `/api/*` (in production, nginx reverse-proxies that path to `app:8000`).

## Security

- `.env`, `vpn/**/wg0.conf`, `data/evidence/`, `data/csv/processing/` are all **gitignored**. Never commit secrets.
- Production: only `:80` and `:443` (nginx) face the public internet. All Docker ports bind to `127.0.0.1` only.
- Streamlit dashboard has no built-in auth — protect `/admin/` with nginx basic-auth or remove that location block entirely.
- Postgres password is required (no insecure default) — `POSTGRES_PASSWORD` must be set in `.env`.

## License

TBD.
