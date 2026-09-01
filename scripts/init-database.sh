#!/bin/bash
# 数据库初始化脚本

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "=========================================="
echo "  数据库初始化"
echo "=========================================="
echo ""

# 获取环境标签
ENV=${1:-development}
log_info "使用环境: $ENV"

# 运行 Python 初始化脚本（统一根 venv）
cd "$(dirname "$0")/.."
uv run python -c "
import sys
sys.path.insert(0, 'backend')
from app.utils.db_init import init_database
init_database(env='$ENV')
"

if [ $? -eq 0 ]; then
    log_success "数据库初始化完成"
else
    log_error "数据库初始化失败"
    exit 1
fi

echo ""
echo "连接信息："
echo "  MySQL: auto_agents@127.0.0.1:3306/auto_agents"
echo "  Redis: 127.0.0.1:6379/0"
echo ""
