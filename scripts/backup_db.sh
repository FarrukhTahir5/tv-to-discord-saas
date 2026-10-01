#!/usr/bin/env bash
# Nightly Postgres backup. Keeps the last 14 dumps.
# Cron (as root):  0 3 * * * /root/tv-to-discord-saas/scripts/backup_db.sh >> /var/log/chartalert-backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-/root/backups/chartalert}"
KEEP=14
mkdir -p "$BACKUP_DIR"

FILE="$BACKUP_DIR/chartapp-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U chartapp chartapp | gzip > "$FILE"

# Fail loudly if the dump is suspiciously small (db down, wrong creds)
if [ "$(stat -c%s "$FILE")" -lt 1024 ]; then
    echo "$(date) backup too small, check db: $FILE" >&2
    exit 1
fi

ls -1t "$BACKUP_DIR"/chartapp-*.sql.gz | tail -n +$((KEEP + 1)) | xargs -r rm --
echo "$(date) backup ok: $FILE"

# Restore:  gunzip -c FILE | docker compose -f docker-compose.prod.yml exec -T db psql -U chartapp chartapp
