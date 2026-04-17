#!/bin/bash

# ============================================================================
# Auto Agents 项目初始化脚本
# 自动检测、安装、配置所需环境
# ============================================================================

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo "=========================================="
echo "  Auto Agents 项目初始化"
echo "=========================================="
echo ""

# ============================================================================
# 1. 检测并安装基础工具
# ============================================================================
log_info "[1/7] 检测基础工具..."

# 检测 Git
if ! command -v git &> /dev/null; then
    log_error "Git 未安装"
    exit 1
fi
log_success "Git 已安装"

# 检测并安装 Homebrew (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v brew &> /dev/null; then
        log_warning "Homebrew 未安装，正在安装..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    log_success "Homebrew 已安装"
fi

# 检测并安装 UV
if ! command -v uv &> /dev/null; then
    log_warning "UV 未安装，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi
log_success "UV 已安装"

# 检测 Python 3.13
if ! uv python list 2>/dev/null | grep -q "3.13"; then
    log_warning "Python 3.13 未安装，正在安装..."
    uv python install 3.13
fi
log_success "Python 3.13 已安装"

# 检测 Node.js
if ! command -v node &> /dev/null; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        log_warning "Node.js 未安装，正在安装..."
        brew install node
    else
        log_error "请手动安装 Node.js 18+"
        exit 1
    fi
fi
log_success "Node.js 已安装"

echo ""

# ============================================================================
# 2. 检测并配置 MySQL 和 Redis
# ============================================================================
log_info "[2/7] 检测数据库服务..."

MYSQL_INSTALLED=false
REDIS_INSTALLED=false

# 检测 MySQL
if command -v mysql &> /dev/null; then
    if mysqladmin ping &>/dev/null; then
        log_success "MySQL 运行中"
        MYSQL_INSTALLED=true
    else
        log_warning "MySQL 已安装但未运行"
        if [[ "$OSTYPE" == "darwin"* ]] && brew services list 2>/dev/null | grep -q mysql; then
            log_info "启动 MySQL..."
            brew services start mysql@8.0 || brew services start mysql
            sleep 5
            if mysqladmin ping &>/dev/null; then
                log_success "MySQL 已启动"
                MYSQL_INSTALLED=true
            fi
        fi
    fi
else
    log_warning "MySQL 未安装"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        read -p "是否安装 MySQL? (y/n): " INSTALL_MYSQL
        if [[ "$INSTALL_MYSQL" == "y" ]]; then
            brew install mysql@8.0
            brew services start mysql@8.0
            sleep 5
            MYSQL_INSTALLED=true
            log_success "MySQL 已安装并启动"
        fi
    fi
fi

# 检测 Redis
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &>/dev/null 2>&1 || redis-cli ping 2>&1 | grep -q "NOAUTH\|PONG"; then
        log_success "Redis 运行中"
        REDIS_INSTALLED=true
    else
        log_warning "Redis 已安装但未运行"
        if [[ "$OSTYPE" == "darwin"* ]] && brew services list 2>/dev/null | grep -q redis; then
            log_info "启动 Redis..."
            brew services start redis
            sleep 2
            if redis-cli ping &>/dev/null 2>&1; then
                log_success "Redis 已启动"
                REDIS_INSTALLED=true
            fi
        fi
    fi
else
    log_warning "Redis 未安装"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        read -p "是否安装 Redis? (y/n): " INSTALL_REDIS
        if [[ "$INSTALL_REDIS" == "y" ]]; then
            brew install redis
            brew services start redis
            sleep 2
            REDIS_INSTALLED=true
            log_success "Redis 已安装并启动"
        fi
    fi
fi

# 初始化数据库
if [ "$MYSQL_INSTALLED" = true ]; then
    echo ""
    log_info "初始化数据库..."
    
    # 获取 MySQL root 密码
    read -sp "请输入 MySQL root 密码（如无密码直接回车）: " DB_ROOT_PASSWORD
    echo ""
    
    # 创建数据库和用户
    if mysql -u root -p"$DB_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS auto_agents CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null; then
        mysql -u root -p"$DB_ROOT_PASSWORD" -e "CREATE USER IF NOT EXISTS 'auto_agents'@'localhost' IDENTIFIED BY 'auto_agents';" 2>/dev/null || true
        mysql -u root -p"$DB_ROOT_PASSWORD" -e "GRANT ALL PRIVILEGES ON auto_agents.* TO 'auto_agents'@'localhost'; FLUSH PRIVILEGES;" 2>/dev/null || true
        log_success "数据库初始化完成"
    else
        log_warning "数据库初始化失败，请手动创建"
    fi
fi

echo ""

# ============================================================================
# 3. 创建项目目录结构
# ============================================================================
log_info "[3/7] 创建目录结构..."

mkdir -p backend/app/{api,models,schemas,services,utils,config}
mkdir -p scrapy/spiders
mkdir -p backend/tests
mkdir -p frontend/admin
mkdir -p frontend/official
mkdir -p skills
mkdir -p rules
mkdir -p scripts
mkdir -p docs

log_success "目录结构创建完成"
echo ""

# ============================================================================
# 4. 初始化 Python 后端
# ============================================================================
log_info "[4/7] 初始化 Python 后端..."

cd backend
uv init --name auto-agents-backend --python 3.13 2>/dev/null || true

# 添加依赖
uv add fastapi uvicorn[standard] pydantic pydantic-settings
uv add scrapy scrapy-redis redis
uv add sqlalchemy pymysql alembic
uv add loguru dynaconf drissionpage selenium httpx python-multipart
uv add --dev pytest pytest-asyncio httpx

cd ..
log_success "Python 环境初始化完成"
echo ""

# ============================================================================
# 5. 创建配置文件
# ============================================================================
log_info "[5/7] 创建配置文件..."

# .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*.so
.Python
.venv/
venv/
*.egg-info/
dist/
build/

# UV
uv.lock

# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# IDE
.vscode/
.idea/
*.swp
*.swo

# Logs
logs/
*.log

# Environment
.env
.env.local
backend/config/.secrets.toml

# OS
.DS_Store
Thumbs.db

# Testing
.coverage
.pytest_cache/
htmlcov/
EOF

log_success "配置文件创建完成"
echo ""

# ============================================================================
# 6. 创建 FastAPI 应用骨架
# ============================================================================
log_info "[6/7] 创建 FastAPI 应用..."

cat > backend/app/main.py << 'EOF'
"""FastAPI 主应用"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings

app = FastAPI(
    title="Auto Agents API",
    description="自动化代理系统 API",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Auto Agents API is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}
EOF

# 创建 __init__.py 文件
touch backend/app/__init__.py
touch backend/app/api/__init__.py
touch backend/app/models/__init__.py
touch backend/app/schemas/__init__.py
touch backend/app/services/__init__.py
touch backend/app/utils/__init__.py
touch backend/app/config/__init__.py

log_success "FastAPI 应用创建完成"
echo ""

# ============================================================================
# 7. 创建启动脚本
# ============================================================================
log_info "[7/7] 创建启动脚本..."

cat > scripts/init-db.sh << 'SCRIPT_EOF'
#!/bin/bash
# 初始化数据库
read -sp "MySQL root 密码: " DB_ROOT_PASSWORD
echo ""
mysql -u root -p"$DB_ROOT_PASSWORD" <<EOF
CREATE DATABASE IF NOT EXISTS auto_agents CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'auto_agents'@'localhost' IDENTIFIED BY 'auto_agents';
GRANT ALL PRIVILEGES ON auto_agents.* TO 'auto_agents'@'localhost';
FLUSH PRIVILEGES;
EOF
echo "数据库初始化完成"
SCRIPT_EOF
chmod +x scripts/init-db.sh

cat > scripts/start.sh << 'SCRIPT_EOF'
#!/bin/bash
# 启动后端服务
cd backend
uv run python -m app.main
SCRIPT_EOF
chmod +x scripts/start.sh

cat > scripts/migrate.sh << 'SCRIPT_EOF'
#!/bin/bash
# 数据库迁移
cd backend
uv run alembic upgrade head
SCRIPT_EOF
chmod +x scripts/migrate.sh

cat > scripts/run-spider.sh << 'SCRIPT_EOF'
#!/bin/bash
# 运行爬虫
SPIDER_NAME=${1:-example}
cd scrapy
uv run scrapy crawl $SPIDER_NAME
SCRIPT_EOF
chmod +x scripts/run-spider.sh

log_success "启动脚本创建完成"
echo ""

# ============================================================================
# 完成
# ============================================================================
echo "=========================================="
log_success "项目初始化完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "  1. 数据库迁移: ./scripts/migrate.sh"
echo "  2. 启动服务:   ./scripts/start.sh"
echo "  3. 访问 API:   http://localhost:8000/docs"
echo ""
