import subprocess
import sys
import os

def main():
    # Reuse the existing Render cron but switch it to the bulk Alpinus crawler.
    # Browser install is idempotent and keeps this compatible with the current Render image.
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    batch = os.getenv("ALPINUS_STAGE3_PHOTO_BATCH", "")
    command = ("alpinus_bulk/photo_stage3_remediation_25.py" if batch == "R25" else
               "alpinus_bulk/photo_stage3_batch7.py" if batch == "007" else
               "alpinus_bulk/photo_stage3_batch6.py" if batch == "006" else
               "alpinus_bulk/photo_stage3_batch5.py" if batch == "005" else
               "alpinus_bulk/photo_stage3_batch4.py" if batch == "004" else
               "alpinus_bulk/photo_stage3_batch3.py" if batch == "003" else
               "alpinus_bulk/photo_stage3_batch2.py" if batch == "002" else
               "alpinus_bulk/photo_stage3_once.py" if batch == "001" else
               "alpinus_bulk/crawl_catalog.py")
    result = subprocess.run([sys.executable, command], check=False)
    return result.returncode

if __name__ == "__main__":
    raise SystemExit(main())
