import subprocess
import sys

def main():
    # Reuse the existing Render cron but switch it to the bulk Alpinus crawler.
    # Browser install is idempotent and keeps this compatible with the current Render image.
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    result = subprocess.run([sys.executable, "alpinus_bulk/crawl_catalog.py"], check=False)
    return result.returncode

if __name__ == "__main__":
    raise SystemExit(main())
