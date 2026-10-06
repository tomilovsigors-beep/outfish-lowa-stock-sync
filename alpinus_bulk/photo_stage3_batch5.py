"""Scoped authenticated Render supplier photo-only runner for Alpinus stage3 batch 005. Never touches Shopify."""
import asyncio
import json
from pathlib import Path
import photo_stage3_once as runner

runner.SELECTED = json.loads(Path("alpinus_bulk/photo_stage3_batch_005_selection.json").read_text(encoding="utf-8"))
runner.DEST = Path("/tmp/alpinus_stage3_photo_batch_005")

if __name__ == "__main__":
    asyncio.run(runner.main())
