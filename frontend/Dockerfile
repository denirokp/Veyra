# Dockerfile для frontend — Vite build + nginx serve.
# Multi-stage: node ставит deps и собирает, nginx раздаёт статику.

FROM node:22-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Runtime — nginx раздаёт собранные файлы из dist.
FROM nginx:alpine

# vite.config.ts proxy не работает в проде, поэтому даём nginx конфиг
# который проксирует /api/* в backend контейнер.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1
