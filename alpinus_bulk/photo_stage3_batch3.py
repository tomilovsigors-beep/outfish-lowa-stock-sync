"""Execute precisely Alpinus stage 3 photo batch 003 using Render B2B auth; no Shopify writes."""
import asyncio
import json
from pathlib import Path
import photo_stage3_once as runner

runner.SELECTED = json.loads(Path("alpinus_bulk/photo_stage3_batch_003_selection.json").read_text(encoding="utf-8"))
runner.DEST = Path("/tmp/alpinus_stage3_photo_batch_003")

if __name__ == "__main__":
    asyncio.run(runner.main())
