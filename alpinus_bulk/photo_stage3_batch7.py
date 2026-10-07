"""Final Alpinus stage 3 mini-batch 007 (2 products), authenticated Render photo-only; no Shopify writes."""
import asyncio
import json
from pathlib import Path
import photo_stage3_once as runner

runner.SELECTED = json.loads(Path("alpinus_bulk/photo_stage3_batch_007_selection.json").read_text(encoding="utf-8"))
runner.DEST = Path("/tmp/alpinus_stage3_photo_batch_007")

if __name__ == "__main__":
    asyncio.run(runner.main())
