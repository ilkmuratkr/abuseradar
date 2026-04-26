#!/bin/bash
# VPN container'da microsocks SOCKS5 proxy başlat
# App/Crawler bu proxy üzerinden dış istekleri VPN tünelinden geçirir

# microsocks yoksa kur
if ! command -v microsocks &> /dev/null; then
    apk add --no-cache build-base git 2>/dev/null || apt-get update && apt-get install -y build-essential git
    cd /tmp
    git clone https://github.com/rofl0r/microsocks.git
    cd microsocks
    make
    cp microsocks /usr/local/bin/
    cd /
    rm -rf /tmp/microsocks
fi

# SOCKS5 proxy başlat (port 1080, tüm interface'lerden erişilebilir)
echo "SOCKS5 proxy başlatılıyor: 0.0.0.0:1080"
microsocks -p 1080 -b 0.0.0.0 &
