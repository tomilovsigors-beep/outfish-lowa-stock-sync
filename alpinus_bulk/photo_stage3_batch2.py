"""Run only the 50 eligible Alpinus supplier products in photo batch 002."""
import asyncio
import json
from pathlib import Path
import photo_stage3_once as runner

runner.SELECTED = json.loads(Path("alpinus_bulk/photo_stage3_batch_002_selection.json").read_text(encoding="utf-8"))
runner.DEST = Path("/tmp/alpinus_stage3_photo_batch_002")

if __name__ == "__main__":
    asyncio.run(runner.main())
