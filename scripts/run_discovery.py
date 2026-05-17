"""Entry point for the discovery phase."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.automation.discovery.har_capture import run_discovery

if __name__ == "__main__":
    asyncio.run(run_discovery())
