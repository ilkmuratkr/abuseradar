.PHONY: up down logs build csv crawl classify contacts monitor dashboard db-shell test clean up-prod down-prod web

# ═══ Docker — dev (default) ═══
up:
	docker compose up -d

down:
	docker compose down

# ═══ Docker — production overlay ═══
up-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

down-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# ═══ Static website (local preview) ═══
web:
	cd web && python3 -m http.server $${PORT_WEB:-8765}

logs:
	docker compose logs -f

build:
	docker compose build --no-cache

# ═══ Servis logları ═══
logs-app:
	docker compose logs -f app

logs-crawler:
	docker compose logs -f crawler

logs-vpn:
	docker compose logs -f vpn-tr vpn-us

# ═══ VPN durumu ═══
vpn-check:
	@echo "VPN-TR:" && docker exec vpn-tr curl -s https://ipinfo.io/json | python3 -m json.tool
	@echo "VPN-US:" && docker exec vpn-us curl -s https://ipinfo.io/json | python3 -m json.tool

# ═══ CSV işleme ═══
csv:
	docker compose exec app python -m csv_processor.cli

# ═══ Pipeline (tek tusla tum akis) ═══
pipeline:
	curl -s -X POST http://localhost:7777/pipeline/run | python3 -m json.tool

pipeline-status:
	curl -s http://localhost:7777/pipeline/status | python3 -m json.tool

attackers:
	curl -s http://localhost:7777/pipeline/attackers | python3 -m json.tool

# ═══ Sınıflandırma ═══
classify:
	curl -s -X POST http://localhost:7777/classify | python3 -m json.tool

classify-multi:
	curl -s -X POST http://localhost:7777/classify/multi-signal | python3 -m json.tool

# ═══ Crawl (VPN-TR üzerinden) ═══
crawl:
	@echo "Kullanım: make crawl-site URL=https://example.com/"

crawl-site:
	docker compose run --rm crawler python -m crawler.cli "$(URL)"

crawl-victims:
	docker compose run --rm crawler python -m crawler.cli --victims

# ═══ İletişim bulma ═══
contacts:
	@echo "Kullanım: make contacts-site DOMAIN=example.com"

contacts-site:
	docker exec vpn-us curl -s -X POST http://localhost:8000/contacts/$(DOMAIN) | python3 -m json.tool

# ═══ Monitoring ═══
monitor:
	docker compose run --rm crawler python -m monitoring.cli

# ═══ İstatistikler ═══
stats:
	@docker exec vpn-us curl -s http://localhost:8000/stats | python3 -m json.tool

victims:
	@docker exec vpn-us curl -s http://localhost:8000/victims | python3 -c \
		"import sys,json; d=json.load(sys.stdin); print(f'Toplam: {d[\"count\"]}'); [print(f'  [{v[\"spam_score\"]}] {v[\"detail\"]}: {v[\"url\"][:90]}') for v in d['victims'][:20]]"

c2:
	@docker exec vpn-us curl -s http://localhost:8000/c2 | python3 -m json.tool

# ═══ Dashboard ═══
dashboard:
	@echo "Dashboard: http://localhost:7778"

# ═══ DB shell ═══
db-shell:
	docker compose exec db psql -U spamwatch -d spamwatch

# ═══ Temizlik ═══
clean:
	docker compose down -v
	rm -rf data/csv/processing/* data/csv/error/*

# ═══ İlk kurulum ═══
init:
	cp .env.example .env
	@echo ".env dosyası oluşturuldu. GEMINI_API_KEY ve RESEND_API_KEY'i düzenleyin."
	mkdir -p data/csv/{inbox,processing,processed,duplicate,error} data/evidence

# ═══ OpenClaw Şikayet ═══
complain-cf:
	@echo "Kullanım: make complain-cf DOMAIN=hacklinkbacklink.com"

complain-cf-domain:
	docker exec vpn-us curl -s -X POST http://localhost:8000/complain/cloudflare/$(DOMAIN) | python3 -m json.tool

complain-all:
	@echo "Kullanım: make complain-all-domain DOMAIN=hacklinkbacklink.com"

complain-all-domain:
	docker exec vpn-us curl -s -X POST http://localhost:8000/complain/all/$(DOMAIN) | python3 -m json.tool

openclaw-logs:
	docker logs openclaw --tail 30

# ═══ Yardım ═══
help:
	@echo "AbuseRadar - Komutlar"
	@echo "========================"
	@echo "make up              → Tüm servisleri başlat (dev)"
	@echo "make up-prod         → Production overlay ile başlat (127.0.0.1 binds)"
	@echo "make down            → Servisleri durdur (dev)"
	@echo "make down-prod       → Servisleri durdur (prod)"
	@echo "make web             → Statik siteyi yerel olarak servisle (port 8765)"
	@echo "make csv             → inbox/ klasöründeki CSV'leri işle"
	@echo "make classify        → Backlink'leri sınıflandır"
	@echo "make crawl-site URL=https://...  → Tek site crawl et (VPN-TR)"
	@echo "make contacts-site DOMAIN=...    → İletişim bilgisi bul"
	@echo "make monitor         → Haftalık monitoring döngüsü"
	@echo "make stats           → İstatistikleri göster"
	@echo "make victims         → Mağdur siteleri listele"
	@echo "make c2              → C2 domainlerini listele"
	@echo "make vpn-check       → VPN IP kontrolü"
	@echo "make dashboard       → Dashboard URL'sini göster"
	@echo "make db-shell        → PostgreSQL shell"
	@echo "make complain-cf-domain DOMAIN=... → CF abuse (OpenClaw)"
	@echo "make complain-all-domain DOMAIN=...→ Tüm şikayetler (OpenClaw)"
	@echo "make openclaw-logs   → OpenClaw logları"
	@echo "make help            → Bu yardım mesajı"
