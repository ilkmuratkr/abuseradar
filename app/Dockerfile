FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI (sadece CLI, daemon değil) — app, openclaw container'ına
# `docker exec ...` ile görev gönderebilsin. docker.sock host'tan mount edilir.
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Public Suffix List'i build sırasında indir → runtime'da network gerektirmesin.
# tldextract'in default cache dizini /tmp olabilir; biz /data altına yönlendirip
# kalıcı volume kullanacağız (compose env: TLDEXTRACT_CACHE).
RUN python -c "import tldextract; tldextract.TLDExtract().update(fetch_now=True)" || true

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
