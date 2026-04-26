"""Monitoring CLI - haftalık döngüyü tetikle."""

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main():
    from .scheduler import run_weekly_cycle

    result = await run_weekly_cycle()
    print(f"\nSonuç: {result}")


if __name__ == "__main__":
    asyncio.run(main())
