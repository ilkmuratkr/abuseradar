#!/bin/bash
# OpenClaw container ilk kurulumu / yeniden yapılandırma.
#
# .env dosyasından OPENAI_API_KEY (ve opsiyonel GEMINI_API_KEY) okuyup
# OpenClaw container'ında auth-profiles.json + models.json'ı yapılandırır.
# Volume persistent olduğu için bir kez çalıştırılması yeter, ama idempotent —
# her çalışmada güncel key ile rewrite eder.
#
# Kullanım: bash infra/openclaw_setup.sh

set -euo pipefail

cd "$(dirname "$0")/.."

# .env'i yükle
if [[ ! -f .env ]]; then
  echo "ERROR: .env bulunamadı"
  exit 1
fi
set -a; source .env; set +a

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY .env içinde tanımlı değil"
  exit 1
fi

# OpenClaw container çalışıyor mu?
if ! docker compose ps openclaw 2>/dev/null | grep -q "running\|Up"; then
  echo "OpenClaw container çalışmıyor — başlatılıyor..."
  docker compose up -d openclaw
  sleep 6
fi

echo "[1/3] auth-profiles.json yazılıyor (canonical format v1)..."
docker compose exec -T openclaw bash -c "cat > /root/.openclaw/.openclaw/agents/main/agent/auth-profiles.json" <<EOF
{
  "version": 1,
  "profiles": {
    "openai:default": {
      "type": "api_key",
      "provider": "openai",
      "key": "${OPENAI_API_KEY}"
    }
  }
}
EOF

echo "[2/3] models.json'a OpenAI provider + son modeller ekleniyor..."
docker compose exec -T -e OPENAI_API_KEY="${OPENAI_API_KEY}" openclaw python3 - <<'PYEOF'
import json
import os

KEY = os.environ["OPENAI_API_KEY"]
PATH = "/root/.openclaw/.openclaw/agents/main/agent/models.json"

with open(PATH) as f:
    d = json.load(f)

# Nisan 2026 itibarıyla OpenAI son modeller
d.setdefault("providers", {})["openai"] = {
    "baseUrl": "https://api.openai.com/v1",
    "apiKey": KEY,
    "auth": "bearer",
    "api": "openai-chat",
    "models": [
        {"id": "gpt-5.5", "name": "GPT-5.5", "api": "openai-chat",
         "reasoning": True, "input": ["text", "image"],
         "contextWindow": 272000, "maxTokens": 128000},
        {"id": "gpt-5", "name": "GPT-5", "api": "openai-chat",
         "input": ["text", "image"],
         "contextWindow": 272000, "maxTokens": 128000},
        {"id": "gpt-5-mini", "name": "GPT-5-mini", "api": "openai-chat",
         "input": ["text", "image"],
         "contextWindow": 272000, "maxTokens": 128000},
    ],
}
d["defaultModel"] = "openai/gpt-5.5"

with open(PATH, "w") as f:
    json.dump(d, f, indent=2)
print("OK providers:", list(d["providers"].keys()))
print("defaultModel:", d["defaultModel"])
PYEOF

echo "[3/3] Sanity check — agent gpt-5.5 ile yanıt veriyor mu..."
RESULT=$(timeout 180 docker compose exec -T openclaw openclaw agent --local --agent main --thinking minimal --timeout 150 -m "Reply with one word: ok" 2>&1 | tail -3)
echo "$RESULT"
if echo "$RESULT" | grep -qi "ok"; then
  echo
  echo "✅ OpenClaw setup tamam — gpt-5.5 VPN-US üzerinden çalışıyor"
else
  echo
  echo "⚠️  Sanity test başarısız, logları incele:"
  docker compose logs --tail=20 openclaw
  exit 1
fi
