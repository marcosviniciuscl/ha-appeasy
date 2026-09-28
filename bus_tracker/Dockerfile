FROM ghcr.io/home-assistant/base:latest

LABEL \
  io.hass.type="app" \
  org.opencontainers.image.authors="Marcos <marcosviniciuscl@outlook.com>" \
  org.opencontainers.image.title="Bus Tracker" \
  org.opencontainers.image.description="Ônibus ao vivo (SIUMobile) com painel, avisos e rastreio no celular." \
  org.opencontainers.image.source="https://github.com/marcosviniciuscl/ha-appeasy"

RUN apk add --no-cache \
    python3 \
    py3-requests \
    tzdata

WORKDIR /app
COPY . .

RUN chmod a+x ./run.sh

CMD ["./run.sh"]
