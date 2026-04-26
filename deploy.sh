#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════
# AbuseRadar — Ubuntu deploy & manage script
#
# Usage:
#   ./deploy.sh ACTION [OPTIONS]
#
# Actions (one of, required):
#   --init                First-time server setup (apt deps, Docker, ufw, clone repo)
#   --update              git pull + rebuild + restart
#   --start               Start the stack (docker compose up -d, prod overlay)
#   --stop                Stop the stack
#   --restart             Restart the stack
#   --status              docker compose ps + VPN egress check
#   --logs [SERVICE]      Tail logs (all services, or SERVICE if given)
#   --check               Preflight: env, vpn configs, disk, ports
#   --backup              pg_dump → /var/backups/abuseradar/
#   --ssl                 Install Let's Encrypt cert via certbot --nginx
#   --nginx               Drop-in /etc/nginx config + reload
#   --systemd             Install boot-time systemd unit
#   --uninstall           Stop stack, remove containers/volumes (KEEPS code & .env)
#   --help, -h            This message
#
# Options:
#   --domain DOMAIN       Public domain (default: abuseradar.org)
#   --email EMAIL         Contact email for Let's Encrypt (default: hello@DOMAIN)
#   --app-dir PATH        Install / target directory (default: /opt/abuseradar)
#   --repo URL            Git repo (default: https://github.com/ilkmuratkr/abuseradar.git)
#   --branch BRANCH       Git branch (default: main)
#   --user USER           Deploy user to create on --init (default: deploy)
#   --no-firewall         Skip ufw configuration in --init
#   --no-ssl              Skip --ssl step inside --init
#   --dry-run             Print what would happen, do nothing
#   -y, --yes             Auto-confirm destructive prompts
#   -v, --verbose         Verbose shell trace (set -x)
#
# Examples:
#   sudo ./deploy.sh --init --domain abuseradar.org --email hello@abuseradar.org
#   ./deploy.sh --update
#   ./deploy.sh --status
#   ./deploy.sh --logs app
#   ./deploy.sh --backup
# ════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Defaults ───────────────────────────────────────────────────────────
DOMAIN="abuseradar.org"
EMAIL=""
APP_DIR="/opt/abuseradar"
REPO_URL="https://github.com/ilkmuratkr/abuseradar.git"
BRANCH="main"
DEPLOY_USER="deploy"
NO_FIREWALL=0
NO_SSL=0
DRY_RUN=0
ASSUME_YES=0
ACTION=""
LOG_SERVICE=""

# ─── Pretty logging ─────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; CYAN=$'\033[36m'; NC=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; CYAN=""; NC=""
fi

log()    { printf '%s\n' "${CYAN}[deploy]${NC} $*"; }
ok()     { printf '%s\n' "${GREEN}[ ok ]${NC} $*"; }
warn()   { printf '%s\n' "${YELLOW}[warn]${NC} $*" >&2; }
err()    { printf '%s\n' "${RED}[fail]${NC} $*" >&2; }
die()    { err "$*"; exit 1; }
hr()     { printf '%s\n' "${DIM}────────────────────────────────────────${NC}"; }

run() {
  if (( DRY_RUN )); then
    printf '%s\n' "${DIM}+ $*${NC}"
  else
    eval "$@"
  fi
}

confirm() {
  local prompt="$1"
  if (( ASSUME_YES )); then return 0; fi
  read -r -p "${YELLOW}${prompt} [y/N]${NC} " ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

require_root() {
  [[ $EUID -eq 0 ]] || die "This action needs root. Re-run with sudo."
}

require_app_dir() {
  [[ -d "$APP_DIR" ]] || die "Project not found at $APP_DIR. Run with --init first or pass --app-dir."
  cd "$APP_DIR"
}

usage() {
  sed -n '2,/^# ═*$/p' "$0" | sed 's/^# \?//'
  exit 0
}

# ─── Argument parsing ───────────────────────────────────────────────────
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --init|--update|--start|--stop|--restart|--status|--check|--backup|--ssl|--nginx|--systemd|--uninstall)
        [[ -n "$ACTION" ]] && die "Multiple actions given: --$ACTION and $1. Pick one."
        ACTION="${1#--}"
        shift
        ;;
      --logs)
        [[ -n "$ACTION" ]] && die "Multiple actions given."
        ACTION="logs"
        shift
        # Optional service name follows; if next arg isn't a flag, take it
        if [[ $# -gt 0 && "${1:0:1}" != "-" ]]; then
          LOG_SERVICE="$1"; shift
        fi
        ;;
      --help|-h) usage ;;
      --domain) DOMAIN="$2"; shift 2 ;;
      --email)  EMAIL="$2"; shift 2 ;;
      --app-dir) APP_DIR="$2"; shift 2 ;;
      --repo)   REPO_URL="$2"; shift 2 ;;
      --branch) BRANCH="$2"; shift 2 ;;
      --user)   DEPLOY_USER="$2"; shift 2 ;;
      --no-firewall) NO_FIREWALL=1; shift ;;
      --no-ssl) NO_SSL=1; shift ;;
      --dry-run) DRY_RUN=1; shift ;;
      -y|--yes) ASSUME_YES=1; shift ;;
      -v|--verbose) set -x; shift ;;
      *) die "Unknown argument: $1 (try --help)" ;;
    esac
  done

  [[ -z "$EMAIL" ]] && EMAIL="hello@${DOMAIN}"
  if [[ -z "$ACTION" ]]; then usage; fi
  return 0
}

# ─── compose helpers ────────────────────────────────────────────────────
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

# ═══════════════════════════════════════════════════════════════════════
# ACTIONS
# ═══════════════════════════════════════════════════════════════════════

action_init() {
  require_root

  log "First-time server setup for ${BOLD}${DOMAIN}${NC} → ${APP_DIR}"
  hr

  log "1/8 · apt update + base tooling"
  run "apt-get update -y"
  run "DEBIAN_FRONTEND=noninteractive apt-get install -y curl git make ca-certificates gnupg ufw fail2ban htop unattended-upgrades"

  log "2/8 · Docker Engine + Compose plugin"
  if ! command -v docker >/dev/null 2>&1; then
    run "curl -fsSL https://get.docker.com | sh"
    ok "Docker installed."
  else
    ok "Docker already present ($(docker --version | head -1))."
  fi

  log "3/8 · Deploy user ${BOLD}${DEPLOY_USER}${NC}"
  if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    run "adduser --disabled-password --gecos '' $DEPLOY_USER"
    run "usermod -aG sudo,docker $DEPLOY_USER"
    if [[ -f /root/.ssh/authorized_keys ]]; then
      run "mkdir -p /home/$DEPLOY_USER/.ssh"
      run "cp /root/.ssh/authorized_keys /home/$DEPLOY_USER/.ssh/"
      run "chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh"
      run "chmod 700 /home/$DEPLOY_USER/.ssh"
      run "chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys"
    fi
    ok "User created. SSH keys copied from root if present."
  else
    run "usermod -aG docker $DEPLOY_USER"
    ok "User $DEPLOY_USER already exists; ensured docker group membership."
  fi

  log "4/8 · Firewall (ufw)"
  if (( NO_FIREWALL )); then
    warn "Skipping ufw (--no-firewall)."
  else
    run "ufw --force reset >/dev/null 2>&1 || true"
    run "ufw default deny incoming"
    run "ufw default allow outgoing"
    run "ufw allow OpenSSH"
    run "ufw allow 80/tcp"
    run "ufw allow 443/tcp"
    run "ufw --force enable"
    ok "Firewall: only SSH, 80, 443 open."
  fi

  log "5/8 · Clone / refresh repo at ${APP_DIR}"
  if [[ -d "$APP_DIR/.git" ]]; then
    ok "Repo already at $APP_DIR; pulling latest"
    run "cd $APP_DIR && git fetch --all && git checkout $BRANCH && git pull --ff-only"
  else
    run "mkdir -p $APP_DIR"
    run "git clone --branch $BRANCH $REPO_URL $APP_DIR"
    run "chown -R $DEPLOY_USER:$DEPLOY_USER $APP_DIR"
    ok "Cloned $REPO_URL ($BRANCH) → $APP_DIR"
  fi

  log "6/8 · .env + VPN configs"
  cd "$APP_DIR"
  if [[ ! -f .env ]]; then
    run "cp .env.example .env"
    warn "Created .env from template — EDIT IT before --start."
    warn "Required: POSTGRES_PASSWORD, GEMINI_API_KEY, RESEND_API_KEY"
    warn "Set: APP_ENV=production, PUBLIC_BASE_URL=https://${DOMAIN}, PORT_BIND=127.0.0.1"
  else
    ok ".env exists; left untouched."
  fi
  for vpn in tr us; do
    if [[ ! -f "vpn/$vpn/wg0.conf" ]]; then
      run "cp vpn/$vpn/wg0.conf.example vpn/$vpn/wg0.conf"
      run "chmod 600 vpn/$vpn/wg0.conf"
      warn "vpn/$vpn/wg0.conf created from template — paste your WireGuard provider config."
    fi
  done

  log "7/8 · nginx"
  if ! command -v nginx >/dev/null 2>&1; then
    run "apt-get install -y nginx"
    ok "nginx installed."
  fi
  action_nginx_install

  log "8/8 · systemd unit"
  action_systemd_install

  hr
  ok "Server prep complete. Next steps:"
  cat <<EOF

  1. Edit secrets:
       \$ \$EDITOR ${APP_DIR}/.env
       \$ \$EDITOR ${APP_DIR}/vpn/tr/wg0.conf
       \$ \$EDITOR ${APP_DIR}/vpn/us/wg0.conf

  2. Start the stack:
       \$ cd ${APP_DIR} && ./deploy.sh --start

  3. Issue SSL certificate (after DNS A-record points to this server):
       \$ ./deploy.sh --ssl --domain ${DOMAIN} --email ${EMAIL}

  4. Verify:
       \$ ./deploy.sh --status
EOF
}

action_start() {
  require_app_dir
  log "Starting stack (production overlay)"
  run "$COMPOSE up -d"
  ok "Stack up. Run --status to verify."
}

action_stop() {
  require_app_dir
  log "Stopping stack"
  run "$COMPOSE down"
  ok "Stack stopped."
}

action_restart() {
  require_app_dir
  log "Restarting stack"
  run "$COMPOSE down"
  run "$COMPOSE up -d"
  ok "Restarted."
}

action_update() {
  require_app_dir
  log "Pulling latest code from $BRANCH"
  run "git fetch --all"
  run "git checkout $BRANCH"
  run "git pull --ff-only"

  log "Rebuilding images"
  run "$COMPOSE build"

  log "Restarting"
  run "$COMPOSE up -d"

  ok "Updated to $(git rev-parse --short HEAD)."
}

action_status() {
  require_app_dir
  log "Compose services"
  run "$COMPOSE ps"

  hr
  log "VPN egress IPs (should be TR + US)"
  if docker ps --format '{{.Names}}' | grep -q '^vpn-tr$'; then
    printf '  vpn-tr: '; docker exec vpn-tr curl -s --max-time 5 https://ipinfo.io/ip 2>/dev/null || echo "n/a"
  fi
  if docker ps --format '{{.Names}}' | grep -q '^vpn-us$'; then
    printf '  vpn-us: '; docker exec vpn-us curl -s --max-time 5 https://ipinfo.io/ip 2>/dev/null || echo "n/a"
  fi

  hr
  log "API health"
  curl -s --max-time 5 http://127.0.0.1:7777/ >/dev/null 2>&1 \
    && ok "API reachable on 127.0.0.1:7777" \
    || warn "API not reachable on 127.0.0.1:7777"

  hr
  log "Disk usage"
  df -h "$APP_DIR" | tail -1
}

action_logs() {
  require_app_dir
  if [[ -n "$LOG_SERVICE" ]]; then
    log "Tailing logs for ${BOLD}${LOG_SERVICE}${NC} (Ctrl-C to exit)"
    run "$COMPOSE logs -f --tail=100 $LOG_SERVICE"
  else
    log "Tailing all logs (Ctrl-C to exit)"
    run "$COMPOSE logs -f --tail=50"
  fi
}

action_check() {
  require_app_dir
  local fails=0

  log "Preflight checks"
  hr

  # .env present and POSTGRES_PASSWORD non-default
  if [[ -f .env ]]; then
    ok ".env present"
    if grep -q '^POSTGRES_PASSWORD=change_me' .env || grep -q '^POSTGRES_PASSWORD=$' .env; then
      err "POSTGRES_PASSWORD is unset or still the example value"; fails=$((fails+1))
    else
      ok "POSTGRES_PASSWORD looks set"
    fi
    if grep -q '^GEMINI_API_KEY=your_gemini' .env; then
      warn "GEMINI_API_KEY still placeholder"
    else
      ok "GEMINI_API_KEY set"
    fi
    if grep -q '^APP_ENV=production' .env; then
      ok "APP_ENV=production"
    else
      warn "APP_ENV is not 'production' — fine for dev, change for server"
    fi
    if grep -q '^PORT_BIND=127.0.0.1' .env; then
      ok "PORT_BIND=127.0.0.1 (nginx-friendly)"
    else
      warn "PORT_BIND is not 127.0.0.1 — services exposed on all interfaces"
    fi
  else
    err ".env missing"; fails=$((fails+1))
  fi

  # VPN configs present and not the example
  for vpn in tr us; do
    local cf="vpn/$vpn/wg0.conf"
    if [[ -f "$cf" ]]; then
      if grep -q 'REPLACE_WITH_YOUR_PRIVATE_KEY' "$cf"; then
        err "$cf still contains template placeholders"; fails=$((fails+1))
      else
        ok "$cf looks configured"
      fi
    else
      err "$cf missing"; fails=$((fails+1))
    fi
  done

  # Docker
  if command -v docker >/dev/null 2>&1; then
    ok "Docker: $(docker --version | head -1)"
  else
    err "Docker not installed"; fails=$((fails+1))
  fi

  # Disk (cross-platform: -k gives 1k blocks on both BSD and GNU)
  local free_gb
  free_gb=$(df -k "$APP_DIR" | awk 'NR==2 {printf "%d", $4/1024/1024}')
  if [[ ${free_gb:-0} -lt 10 ]]; then
    warn "Less than 10 GB free in $APP_DIR (${free_gb} GB)"
  else
    ok "Disk: ${free_gb} GB free"
  fi

  # Ports we'd want free
  for p in 80 443; do
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE ":${p}\$"; then
      ok "Port $p in use (probably nginx — fine)"
    else
      warn "Port $p free (nginx not listening yet)"
    fi
  done

  hr
  if (( fails > 0 )); then
    err "$fails check(s) failed"
    exit 1
  else
    ok "All checks passed"
  fi
}

action_backup() {
  require_app_dir
  local dest="/var/backups/abuseradar"
  local stamp; stamp=$(date +%F-%H%M%S)
  local file="${dest}/db-${stamp}.sql.gz"

  log "Backing up Postgres → $file"
  run "mkdir -p $dest"
  if (( DRY_RUN )); then
    printf '+ %s\n' "$COMPOSE exec -T db pg_dump … | gzip > $file"
  else
    $COMPOSE exec -T db pg_dump -U "${POSTGRES_USER:-spamwatch}" "${POSTGRES_DB:-spamwatch}" | gzip > "$file"
    chmod 600 "$file"
    ok "Wrote $(du -h "$file" | cut -f1) to $file"
    log "Pruning backups older than 30 days"
    run "find $dest -name 'db-*.sql.gz' -mtime +30 -delete"
  fi
}

action_nginx_install() {
  require_root
  local src="$APP_DIR/infra/nginx/abuseradar.conf"
  local dst="/etc/nginx/sites-available/abuseradar.conf"
  [[ -f "$src" ]] || die "Missing $src — is the repo at $APP_DIR?"

  log "Installing nginx config (domain: ${BOLD}${DOMAIN}${NC})"
  run "sed 's/abuseradar\\.org/${DOMAIN}/g; s/www\\.${DOMAIN}/www.${DOMAIN}/g' $src > $dst"
  run "ln -sf $dst /etc/nginx/sites-enabled/abuseradar.conf"
  run "rm -f /etc/nginx/sites-enabled/default"

  if [[ ! -e /var/www/abuseradar/web ]]; then
    run "mkdir -p /var/www/abuseradar"
    run "ln -sfn $APP_DIR/web /var/www/abuseradar/web"
    run "chown -R www-data:www-data /var/www/abuseradar"
  fi

  if (( ! DRY_RUN )); then
    if nginx -t 2>&1 | tail -2; then
      run "systemctl reload nginx"
      ok "nginx reloaded"
    else
      err "nginx config test failed — fix manually"
    fi
  fi
}

action_nginx() { action_nginx_install; }

action_ssl() {
  require_root
  if (( NO_SSL )); then warn "Skipping SSL (--no-ssl)"; return; fi

  log "Installing certbot if needed"
  if ! command -v certbot >/dev/null 2>&1; then
    run "apt-get install -y certbot python3-certbot-nginx"
  fi

  log "Requesting Let's Encrypt cert for ${DOMAIN} + www"
  run "certbot --nginx -n --agree-tos --redirect --email $EMAIL -d $DOMAIN -d www.$DOMAIN"
  ok "SSL installed; auto-renew via /etc/cron.d/certbot."
}

action_systemd_install() {
  require_root
  local src="$APP_DIR/infra/systemd/abuseradar.service"
  local dst="/etc/systemd/system/abuseradar.service"
  [[ -f "$src" ]] || die "Missing $src — is the repo at $APP_DIR?"

  log "Installing systemd unit"
  run "sed 's|/opt/abuseradar|${APP_DIR}|g' $src > $dst"
  run "systemctl daemon-reload"
  run "systemctl enable abuseradar.service"
  ok "Boot-time auto-start enabled. Service: abuseradar.service"
}

action_systemd() { action_systemd_install; }

action_uninstall() {
  require_app_dir
  warn "This will: stop containers, drop volumes (incl. Postgres data), remove networks."
  warn "It will NOT remove: code, .env, vpn/*.conf, data/evidence."
  confirm "Proceed?" || { log "Cancelled."; return; }

  log "Removing stack + volumes"
  run "$COMPOSE down -v --remove-orphans"
  ok "Uninstalled. Re-run --start to bring back from a clean Postgres."
}

# ═══════════════════════════════════════════════════════════════════════
# Dispatch
# ═══════════════════════════════════════════════════════════════════════

main() {
  parse_args "$@"

  if (( DRY_RUN )); then
    warn "DRY-RUN mode — no commands will actually execute"
  fi

  case "$ACTION" in
    init)       action_init ;;
    start)      action_start ;;
    stop)       action_stop ;;
    restart)    action_restart ;;
    update)     action_update ;;
    status)     action_status ;;
    logs)       action_logs ;;
    check)      action_check ;;
    backup)     action_backup ;;
    ssl)        action_ssl ;;
    nginx)      action_nginx ;;
    systemd)    action_systemd ;;
    uninstall)  action_uninstall ;;
    *)          die "Unknown action: $ACTION (try --help)" ;;
  esac
}

main "$@"
