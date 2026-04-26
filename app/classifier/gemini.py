"""Gemini 3.1 Pro ile belirsiz backlink'leri sınıflandır."""

import json
import logging

from google import genai

from config import settings

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """Aşağıdaki backlink verisini analiz et.
Bu backlink meşru mi yoksa SEO spam enjeksiyonu mu?

Referring URL: {referring_url}
Referring Title: {referring_title}
Anchor Text: {anchor_text}
Platform: {platform}
Is Spam Flag: {is_spam_flag}
Rendered: {is_rendered}
Raw: {is_raw}
Left Context: {left_context}
Right Context: {right_context}
Page Category: {page_category}

Sadece JSON yanıt ver:
{{"category": "MAGDUR|SALDIRGAN|ARAC", "detail": "kısa açıklama", "confidence": 0-100}}
"""


async def classify_with_gemini(backlink: dict) -> dict:
    """Tek bir backlink'i Gemini ile sınıflandır."""
    if not settings.gemini_api_key:
        logger.warning("Gemini API key yok, BELIRSIZ olarak bırakılıyor")
        return {"category": "BELIRSIZ", "detail": "api_key_yok", "confidence": 0}

    try:
        client = genai.Client(api_key=settings.gemini_api_key)

        prompt = CLASSIFICATION_PROMPT.format(
            referring_url=backlink.get("referring_url", ""),
            referring_title=backlink.get("referring_title", ""),
            anchor_text=backlink.get("anchor_text", ""),
            platform=backlink.get("platform", ""),
            is_spam_flag=backlink.get("is_spam_flag", ""),
            is_rendered=backlink.get("is_rendered", ""),
            is_raw=backlink.get("is_raw", ""),
            left_context=backlink.get("left_context", ""),
            right_context=backlink.get("right_context", ""),
            page_category=backlink.get("page_category", ""),
        )

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config={
                "temperature": 0.1,
                "max_output_tokens": 200,
            },
        )

        text = response.text.strip()
        # JSON parse
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)

        return {
            "category": result.get("category", "BELIRSIZ"),
            "detail": result.get("detail", "gemini_siniflandirdi"),
            "confidence": result.get("confidence", 50),
        }

    except Exception as e:
        logger.error(f"Gemini sınıflandırma hatası: {e}")
        return {"category": "BELIRSIZ", "detail": f"gemini_hata: {e}", "confidence": 0}
