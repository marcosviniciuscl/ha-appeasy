FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache python3 py3-requests py3-websocket-client tzdata
WORKDIR /app
COPY . .
RUN chmod +x run.sh
CMD ["./run.sh"]
