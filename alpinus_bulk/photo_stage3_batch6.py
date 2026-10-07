"""Scoped authenticated Render supplier photo-only runner for Alpinus stage3 batch 006. No Shopify writes."""
import asyncio
import json
from pathlib import Path
import photo_stage3_once as runner

runner.SELECTED = json.loads(Path("alpinus_bulk/photo_stage3_batch_006_selection.json").read_text(encoding="utf-8"))
runner.DEST = Path("/tmp/alpinus_stage3_photo_batch_006")

if __name__ == "__main__":
    asyncio.run(runner.main())
