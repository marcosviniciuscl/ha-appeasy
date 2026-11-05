FROM node:22-alpine AS panel

WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build


FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-requests py3-websocket-client tzdata
WORKDIR /app
COPY . .
COPY --from=panel /web ./web
RUN chmod +x run.sh
CMD ["./run.sh"]
