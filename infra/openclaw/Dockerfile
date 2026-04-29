# OpenClaw + Chromium (browser-automation skill için).
# Base alpine/openclaw:latest debian-bookworm tabanlı. Resmi image'da
# Chrome/Chromium yok → browser-automation skill çağrıları "No supported
# browser found" hatası veriyor. Bu Dockerfile chromium + bağımlılıklarını
# ekler, headless modda çalışır.

FROM alpine/openclaw:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium \
      chromium-driver \
      fonts-liberation \
      fonts-noto-color-emoji \
      libnss3 \
      libxss1 \
      libasound2 \
      libatk1.0-0 \
      libatk-bridge2.0-0 \
      libcups2 \
      libdrm2 \
      libgbm1 \
      libpango-1.0-0 \
      libxkbcommon0 \
      libxcomposite1 \
      libxdamage1 \
      libxrandr2 \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/* \
    && chromium --version

# OpenClaw browser-automation skill chromium'u path'te arar.
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMIUM_BIN=/usr/bin/chromium \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    PLAYWRIGHT_BROWSERS_PATH=/usr/bin

# Sandbox kapatıcı flag — root'un container'da çalışması için
ENV CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage --disable-gpu --headless=new"
