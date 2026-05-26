# ai-lab-mcp — MCP-сервер AI Lab. Тонкий фасад, ходит в backend по HTTP.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# Транспорт streamable-http; порт настраивается через AILAB_MCP_PORT.
EXPOSE 8765

CMD ["python", "server.py"]
