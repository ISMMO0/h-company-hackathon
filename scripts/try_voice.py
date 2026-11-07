"""Manual test: speak once, see partials, get the final text.

    .venv/bin/python scripts/try_voice.py
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from brain import voice


async def main() -> None:
    print("Speak now…")
    text = await voice.listen_once(on_partial=lambda t: print(f"  … {t}"))
    print(f"Final: {text!r}" if text else "Final: (nothing heard)")


if __name__ == "__main__":
    asyncio.run(main())
