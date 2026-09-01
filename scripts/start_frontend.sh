#!/bin/bash
echo "启动后台管理系统..."
cd frontend/admin
npm start &

echo "启动官方网站..."
cd ../official
npm start
