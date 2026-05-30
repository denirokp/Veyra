#!/bin/bash
# Запуск backend в фоне + MCP в foreground. Если backend упадёт — контейнер живёт
# (MCP отдаст "backend_unreachable" через health()), Fly не перезапустит зря.
set -e

echo "[entrypoint] starting backend on :8000..."
cd /app/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "[entrypoint] waiting for backend health..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "[entrypoint] backend ready (after ${i}s)"
        break
    fi
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "[entrypoint] FATAL: backend died during startup"
        exit 1
    fi
    sleep 1
done

echo "[entrypoint] starting MCP on :${AILAB_MCP_PORT:-8765}..."
cd /app/ai-lab-mcp
exec python server.py
