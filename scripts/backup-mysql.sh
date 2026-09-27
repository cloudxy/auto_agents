#!/usr/bin/env bash
# MySQL 逻辑备份：single-transaction + gzip；保留 7 日日备 + 4 周周备。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${BACKUP_DIR:-$ROOT/runtime/backups/mysql}"
mkdir -p "$DEST/daily" "$DEST/weekly"
STAMP="$(date +%Y%m%d_%H%M%S)"
HOST="${MYSQL_HOST:-127.0.0.1}"
PORT="${MYSQL_PORT:-3306}"
USER="${MYSQL_USER:-auto_agents}"
DB="${MYSQL_DATABASE:-auto_agents}"
FILE="$DEST/daily/auto_agents_${STAMP}.sql.gz"
mysqldump --single-transaction --routines --triggers \
  -h "$HOST" -P "$PORT" -u "$USER" -p"${MYSQL_PASSWORD:?set MYSQL_PASSWORD}" \
  "$DB" | gzip -c > "$FILE"
ln -sfn "$FILE" "$DEST/latest.sql.gz"
# 周备：周日复制一份
if [[ "$(date +%u)" == "7" ]]; then
  cp "$FILE" "$DEST/weekly/auto_agents_week_$(date +%Y%W).sql.gz"
fi
# 保留策略
find "$DEST/daily" -name '*.sql.gz' -mtime +7 -delete
find "$DEST/weekly" -name '*.sql.gz' -mtime +28 -delete
echo "backup ok: $FILE"
# 空跑校验：gzip 头完整
gzip -t "$FILE"
