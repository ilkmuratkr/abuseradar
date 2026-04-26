# Deploying AbuseRadar to an Ubuntu server

Tested on Ubuntu 22.04 LTS and 24.04 LTS. Works on any cloud provider (Hetzner, OVH, AWS, DigitalOcean) with at least:

- 4 vCPUs
- 8 GB RAM
- 80 GB SSD
- Public IPv4

This guide assumes the domain `abuseradar.org` (replace with yours) is already pointed at the server's IP via an `A` record at your DNS provider.

---

## 1. Server prep

```bash
ssh root@your-server-ip   # or a sudo user

# Updates + basics
apt update && apt upgrade -y
apt install -y curl git ufw fail2ban htop unattended-upgrades

# Create a non-root deploy user
adduser deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys

# Lock down SSH (optional but recommended)
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# Firewall: only SSH + HTTP + HTTPS
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

Switch to the deploy user from here on:

```bash
ssh deploy@your-server-ip
```

## 2. Install Docker

```bash
# Official Docker install
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker            # or log out and back in

# Verify
docker run --rm hello-world
docker compose version
```

## 3. Clone the repo

```bash
sudo mkdir -p /opt/abuseradar
sudo chown $USER:$USER /opt/abuseradar
git clone git@github.com:<you>/abuseradar.git /opt/abuseradar
cd /opt/abuseradar
```

## 4. Configure environment

```bash
cp .env.example .env
$EDITOR .env
```

Set at minimum:

```
APP_ENV=production
PROJECT_DOMAIN=abuseradar.org
PUBLIC_BASE_URL=https://abuseradar.org

POSTGRES_PASSWORD=<generate with: openssl rand -base64 32>
GEMINI_API_KEY=<from https://aistudio.google.com/apikey>
RESEND_API_KEY=<from https://resend.com after verifying the domain>

PORT_BIND=127.0.0.1   # nginx will reverse-proxy
```

## 5. WireGuard configs

```bash
cp vpn/tr/wg0.conf.example vpn/tr/wg0.conf
cp vpn/us/wg0.conf.example vpn/us/wg0.conf
$EDITOR vpn/tr/wg0.conf vpn/us/wg0.conf
chmod 600 vpn/tr/wg0.conf vpn/us/wg0.conf
```

Use any WireGuard provider with TR and US endpoints (Mullvad, AzireVPN, IVPN). Paste the provider's config verbatim.

## 6. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose ps                             # all services healthy?
docker compose logs -f app crawler            # watch boot
```

Verify VPN egress IPs:

```bash
make vpn-check
# Should print Turkey IP for vpn-tr and US IP for vpn-us
```

## 7. nginx + Let's Encrypt

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Drop in the config:

```bash
sudo cp infra/nginx/abuseradar.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/abuseradar.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Get certs:

```bash
sudo certbot --nginx -d abuseradar.org -d www.abuseradar.org
# Choose redirect (option 2). Certbot will rewrite the config and reload nginx.
sudo systemctl status certbot.timer            # auto-renew installed
```

Deploy the static website:

```bash
sudo mkdir -p /var/www/abuseradar
sudo ln -s /opt/abuseradar/web /var/www/abuseradar/web
sudo chown -R www-data:www-data /var/www/abuseradar
```

> Alternative: skip nginx and use **Caddy** — auto-SSL, simpler config. See `infra/Caddyfile`.

## 8. Optional: protect the admin paths

The Streamlit dashboard at `/admin/` ships with no auth. Either remove that location block from `infra/nginx/abuseradar.conf`, or put basic auth in front:

```bash
sudo apt install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd analyst
# uncomment the auth_basic lines in /etc/nginx/sites-available/abuseradar.conf
sudo systemctl reload nginx
```

## 9. Boot-time auto-start

```bash
sudo cp infra/systemd/abuseradar.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now abuseradar.service
sudo systemctl status abuseradar.service
```

After a server reboot, the stack comes back up automatically.

## 10. Backups

The only stateful Docker volume is `pgdata`. Back it up to S3-compatible storage daily:

```bash
# Add to /etc/cron.d/abuseradar-backup
0 3 * * * deploy cd /opt/abuseradar && \
  docker compose exec -T db pg_dump -U spamwatch spamwatch | \
  gzip > /var/backups/abuseradar/db-$(date +\%F).sql.gz && \
  find /var/backups/abuseradar -name 'db-*.sql.gz' -mtime +30 -delete
```

Also worth backing up: `data/evidence/` (rendered DOM/screenshots) and `data/openclaw-workspace/`.

## 11. Updates

```bash
cd /opt/abuseradar
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

For a static-only site change (HTML/CSS/JS), nothing to rebuild — nginx serves the new files immediately.

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| Site loads but `/api/` 502s | `docker compose ps app` — is the container up? `docker compose logs app` |
| VPN unhealthy | `docker compose logs vpn-tr` — wg0.conf valid? Provider endpoint reachable? |
| `make vpn-check` returns wrong country | The microsocks proxy hasn't started yet; wait 30 s and retry |
| Certbot fails | DNS A-record missing or not propagated. Check with `dig abuseradar.org` |
| Streamlit `/admin/` blank | Add the websocket headers (already in `abuseradar.conf`) and reload nginx |
| Postgres won't start | Old `pgdata` volume from an earlier password — `docker compose down -v` if it's safe to wipe |

## 13. Mac / Ubuntu differences (one-pager)

| | Mac (Docker Desktop) | Ubuntu (Docker Engine) |
|---|---|---|
| `host.docker.internal` | Resolves automatically | Needs `extra_hosts: host-gateway` (already set) |
| File permissions | Docker Desktop translates | Honors PUID/PGID (set to 1000:1000) |
| WireGuard kernel module | Container ships its own (works fine) | Kernel module auto-loaded; no extra setup |
| Public ports | Bind to all interfaces by default | Same — but with `PORT_BIND=127.0.0.1` we restrict to localhost in prod |
| systemd | Not used | `infra/systemd/abuseradar.service` for boot-time auto-start |

The codebase is identical on both. The only operational difference is the `PORT_BIND` env (empty in dev, `127.0.0.1` in prod) and the optional nginx + systemd layer for production.
