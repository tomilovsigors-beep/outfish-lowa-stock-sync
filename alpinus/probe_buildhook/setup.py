import subprocess
import sys
from pathlib import Path
from setuptools import setup

probe = Path(__file__).resolve().parent.parent / "probe.py"
result = subprocess.run([sys.executable, str(probe)], check=False)
print(f"ALPINUS_BULK_BUILD_EXIT={result.returncode}", flush=True)

setup(name="alpinus-browser-diag-hook", version="0.0.2", py_modules=[])
