"""Crawler worker - ileride doldurulacak."""

import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Crawler worker başlatıldı. Görev bekleniyor...")
    while True:
        time.sleep(60)
