import subprocess
import sys
import os

def main():
    # Reuse the existing Render cron but switch it to the bulk Alpinus crawler.
    # Browser install is idempotent and keeps this compatible with the current Render image.
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    photo_mode = os.getenv("ALPINUS_STAGE3_PHOTO_BATCH", "") == "001"
    command = "alpinus_bulk/photo_stage3_once.py" if photo_mode else "alpinus_bulk/crawl_catalog.py"
    result = subprocess.run([sys.executable, command], check=False)
    return result.returncode

if __name__ == "__main__":
    raise SystemExit(main())
