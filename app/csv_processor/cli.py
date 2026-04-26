"""CSV işleme CLI komutu."""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main():
    from .parser import process_inbox

    results = await process_inbox()

    completed = [r for r in results if r["status"] == "completed"]
    skipped = [r for r in results if r["status"] == "skipped"]

    print(f"\n{'='*60}")
    print(f"CSV İşleme Tamamlandı")
    print(f"{'='*60}")
    print(f"İşlenen: {len(completed)}")
    print(f"Atlanan (duplicate): {len(skipped)}")

    for r in completed:
        print(f"  ✓ {r['filename']}: {r['new']} yeni, {r['skipped']} mevcut")

    for r in skipped:
        print(f"  ⊘ {r['filename']}: {r['reason']}")


if __name__ == "__main__":
    asyncio.run(main())
