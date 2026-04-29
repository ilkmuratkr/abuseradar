FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Public Suffix List'i build sırasında indir → runtime'da network gerektirmesin.
# tldextract'in default cache dizini /tmp olabilir; biz /data altına yönlendirip
# kalıcı volume kullanacağız (compose env: TLDEXTRACT_CACHE).
RUN python -c "import tldextract; tldextract.TLDExtract().update(fetch_now=True)" || true

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
