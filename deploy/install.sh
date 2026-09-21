#!/usr/bin/env bash
# Leaf Standard module for Field Diary - installer (AlmaLinux + cPanel + Apache + PostgreSQL)
#
#   cd /root/leaf_standard && \
#   DOMAIN=your.domain CPUSER=cpaneluser bash deploy/install.sh
#
# Optional env:
#   APP_DIR=/opt/saduai/leaf_standard   PORT=8015   PREFIX=/field-diary/leaf-standard
#   DB_URL=postgresql+psycopg2://user:pass@127.0.0.1:5432/field_diary   (else auto-created user in field_diary DB)
#   FERT_ORIGIN=https://your.domain   (origin of the Fertilizer app page that embeds the table)
# Safe to re-run: keeps .env, users and data.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/saduai/leaf_standard}"
PREFIX="${PREFIX:-/field-diary/leaf-standard}"; PREFIX="/${PREFIX#/}"; PREFIX="${PREFIX%/}"
DOMAIN="${DOMAIN:?set DOMAIN=your.domain}"
CPUSER="${CPUSER:?set CPUSER=cpanel_username}"
SERVICE=leaf-standard
PY="$(command -v python3.11 || command -v python3.12 || command -v python3)"
log(){ printf '\033[1;32m==>\033[0m %s\n' "$*"; }

[ "$(id -u)" = 0 ] || { echo "Run as root"; exit 1; }
"$PY" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ needed"'

# ---- port
if [ -z "${PORT:-}" ]; then
  if [ -f "$APP_DIR/.port" ]; then PORT=$(cat "$APP_DIR/.port")
  else for p in $(seq 8015 8040); do ss -ltn | grep -q ":$p " || { PORT=$p; break; }; done; fi
fi
log "Port $PORT"

# ---- files
log "Copying app to $APP_DIR"
mkdir -p "$APP_DIR"
cp -r "$SRC/app" "$SRC/static" "$SRC/deploy" "$SRC/requirements.txt" "$APP_DIR/"
rm -f "$APP_DIR/static/test_host.html"
echo "$PORT" > "$APP_DIR/.port"

# ---- venv
log "Python venv"
[ -d "$APP_DIR/venv" ] || "$PY" -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# ---- database (same field_diary DB, tables prefixed ls_)
ENVF="$APP_DIR/.env"
if [ ! -f "$ENVF" ]; then
  if [ -z "${DB_URL:-}" ]; then
    log "Creating PostgreSQL role leaf_standard in field_diary"
    DBPW=$(openssl rand -hex 16)
    su - postgres -c "psql -v ON_ERROR_STOP=1 -d field_diary" <<SQL
DO \$\$BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='leaf_standard') THEN
    CREATE ROLE leaf_standard LOGIN PASSWORD '$DBPW';
  ELSE
    ALTER ROLE leaf_standard PASSWORD '$DBPW';
  END IF;
END\$\$;
GRANT CONNECT ON DATABASE field_diary TO leaf_standard;
GRANT USAGE, CREATE ON SCHEMA public TO leaf_standard;
SQL
    DB_URL="postgresql+psycopg2://leaf_standard:${DBPW}@127.0.0.1:5432/field_diary"
    # allow md5 login from localhost for this role (kept by the pg_hba guard too)
    HBA=$(su - postgres -c "psql -Atc 'show hba_file'")
    if ! grep -q 'leaf_standard' "$HBA"; then
      sed -i "1i host    field_diary    leaf_standard    127.0.0.1/32    md5" "$HBA"
      su - postgres -c "psql -Atc 'select pg_reload_conf()'" >/dev/null
    fi
    if [ -f /root/fix-pg-hba.sh ] && ! grep -q leaf_standard /root/fix-pg-hba.sh; then
      cp /root/fix-pg-hba.sh /root/fix-pg-hba.sh.bak.$(date +%s)
      cat >> /root/fix-pg-hba.sh <<'G'

# leaf_standard (Field Diary - Leaf Standard module)
HBA_LS=$(su - postgres -c "psql -Atc 'show hba_file'")
grep -q 'leaf_standard' "$HBA_LS" || { sed -i "1i host    field_diary    leaf_standard    127.0.0.1/32    md5" "$HBA_LS"; su - postgres -c "psql -Atc 'select pg_reload_conf()'" >/dev/null; }
G
      log "Added leaf_standard rule to /root/fix-pg-hba.sh (backup kept)"
    fi
  fi
  ORIGINS="${FERT_ORIGIN:-https://$DOMAIN}"
  cat > "$ENVF" <<E
LS_DATABASE_URL=$DB_URL
LS_SECRET_KEY=$(openssl rand -hex 32)
LS_EMBED_KEY=$(openssl rand -hex 20)
LS_CORS_ORIGINS=$ORIGINS
LS_URL_PREFIX=$PREFIX
LS_TARGET=0.70
LS_WARN=0.60
LS_EDIT_DAYS=1
LS_TZ=Asia/Colombo
E
  chmod 600 "$ENVF"
  log ".env written"
else
  log ".env exists - kept"
fi

# ---- tables + first users
cd "$APP_DIR"
log "Creating tables"
venv/bin/python -m app.cli init
CRED=/root/leaf_standard_credentials.txt
if ! venv/bin/python -m app.cli list | grep -q ' admin '; then
  EPW=$(openssl rand -base64 9 | tr -dc 'A-Za-z0-9' | head -c 10)
  APW=$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 14)
  CPW=$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 12)
  venv/bin/python -m app.cli create-estate-users "$EPW" >/dev/null
  venv/bin/python -m app.cli add-user admin "$APW" admin "SADUAI Admin" >/dev/null
  venv/bin/python -m app.cli add-user ceo "$CPW" ceo "CEO" >/dev/null
  {
    echo "Leaf Standard users  ($(date))"
    echo "URL: https://$DOMAIN$PREFIX/"
    echo "admin / $APW"
    echo "ceo   / $CPW"
    echo "estate users (calsay, clarendon, dessford, somerset, greatwestern, mattakelle, palmerston,"
    echo "  radella, bearwell, holyrood, logie, wattegoda, moragalla, deniyaya, indola, kiruwanaganga)"
    echo "  first password for all: $EPW   -> change each in $PREFIX/admin"
  } > "$CRED"; chmod 600 "$CRED"
  log "Users created -> $CRED"
fi

# ---- systemd
log "systemd service $SERVICE"
cat > /etc/systemd/system/$SERVICE.service <<U
[Unit]
Description=SADUAI Field Diary - Leaf Standard
After=network.target postgresql.service

[Service]
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORT --workers 2 --proxy-headers
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
U
systemctl daemon-reload
systemctl enable --now $SERVICE
systemctl restart $SERVICE
sleep 2
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null && log "Service healthy on :$PORT" || { journalctl -u $SERVICE -n 40 --no-pager; exit 1; }

# ---- Apache (cPanel userdata: std + ssl so both http/https work)
CONF_BODY="# Field Diary - Leaf Standard (managed by leaf_standard/deploy/install.sh)
<IfModule mod_proxy.c>
  ProxyPreserveHost On
  RedirectMatch 301 ^$PREFIX\$ $PREFIX/
  ProxyPass        $PREFIX/ http://127.0.0.1:$PORT/ retry=0 timeout=120
  ProxyPassReverse $PREFIX/ http://127.0.0.1:$PORT/
</IfModule>"
for kind in std ssl; do
  D=/etc/apache2/conf.d/userdata/$kind/2_4/$CPUSER/$DOMAIN
  mkdir -p "$D"
  echo "$CONF_BODY" > "$D/leaf_standard.conf"
done
log "Apache include written (std + ssl)"
if [ -x /usr/local/cpanel/scripts/rebuildhttpdconf ]; then
  /usr/local/cpanel/scripts/rebuildhttpdconf >/dev/null
fi
if apachectl -t 2>/dev/null || httpd -t 2>/dev/null; then
  /usr/local/cpanel/scripts/restartsrv_httpd >/dev/null 2>&1 || systemctl reload httpd
  log "Apache reloaded"
else
  echo "!! Apache config test failed - check the output of: apachectl -t"; exit 1
fi

sleep 1
code=$(curl -ks -o /dev/null -w '%{http_code}' "https://$DOMAIN$PREFIX/api/config" || true)
log "Public check https://$DOMAIN$PREFIX/api/config -> HTTP $code"

EMBED=$(grep LS_EMBED_KEY "$ENVF" | cut -d= -f2)
cat <<DONE

============================================================
 Leaf Standard installed
 Estate entry : https://$DOMAIN$PREFIX/
 CEO dashboard: https://$DOMAIN$PREFIX/dashboard
 Users admin  : https://$DOMAIN$PREFIX/admin
 Logins       : $CRED

 Fertilizer app CEO dashboard - paste:
   <div id="leaf-standard" data-src="https://$DOMAIN$PREFIX/" data-key="$EMBED"></div>
   <script src="https://$DOMAIN$PREFIX/static/widget.js" defer></script>
============================================================
DONE
