#!/bin/bash
# 初始化数据库
read -sp "MySQL root 密码: " DB_ROOT_PASSWORD
echo ""
mysql -u root -p"$DB_ROOT_PASSWORD" <<EOF
CREATE DATABASE IF NOT EXISTS auto_agents CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'auto_agents'@'localhost' IDENTIFIED BY '123456';
GRANT ALL PRIVILEGES ON auto_agents.* TO 'auto_agents'@'localhost';
FLUSH PRIVILEGES;
EOF
echo "数据库初始化完成"
