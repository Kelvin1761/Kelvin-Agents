"""
Auto-Regenerate Dashboard — Watches for new/modified analysis files
and automatically regenerates the static Open Dashboard.html.

Usage:
    python3 auto_regenerate.py          # Run in foreground
    python3 auto_regenerate.py --daemon  # Run as background daemon
"""
import os
import sys
import time
import signal
import logging
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Paths
DASHBOARD_DIR = Path(__file__).resolve().parent
ANTIGRAVITY_ROOT = DASHBOARD_DIR.parent
GENERATE_SCRIPT = DASHBOARD_DIR / "generate_static.py"
PID_FILE = DASHBOARD_DIR / "logs" / "auto_regenerate.pid"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AutoRegen] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class AnalysisFileHandler(FileSystemEventHandler):
    """Watches for *Analysis*.txt file changes and triggers regeneration."""

    def __init__(self):
        super().__init__()
        self._last_trigger = 0
        self._debounce_seconds = 5  # Wait for file writes to settle

    def _is_analysis_file(self, path: str) -> bool:
        p = Path(path)
        return (
            p.suffix in (".txt", ".md")
            and "Analysis" in p.name
            and not p.name.startswith(".")
        )

    def _debounced_regenerate(self, event_path: str):
        now = time.time()
        if now - self._last_trigger > self._debounce_seconds:
            self._last_trigger = now
            logger.info(f"Change detected: {Path(event_path).name}")
            regenerate()

    def on_created(self, event):
        if not event.is_directory and self._is_analysis_file(event.src_path):
            self._debounced_regenerate(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._is_analysis_file(event.src_path):
            self._debounced_regenerate(event.src_path)


def regenerate():
    """Run generate_static.py to rebuild Open Dashboard.html."""
    logger.info("Regenerating static dashboard...")
    try:
        result = subprocess.run(
            [sys.executable, str(GENERATE_SCRIPT)],
            cwd=str(DASHBOARD_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("Dashboard regenerated successfully")
        else:
            logger.error(f"Regeneration failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("Regeneration timed out after 60s")
    except Exception as e:
        logger.error(f"Regeneration error: {e}")


def write_pid():
    """Write PID file for stop script."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def cleanup_pid(*_):
    """Remove PID file on exit."""
    if PID_FILE.exists():
        PID_FILE.unlink()
    sys.exit(0)


def main():
    # Write PID for stop script
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, cleanup_pid)
    signal.signal(signal.SIGINT, cleanup_pid)

    watch_path = str(ANTIGRAVITY_ROOT)
    logger.info(f"Watching: {watch_path}")
    logger.info("Will regenerate Open Dashboard.html when analysis files change")

    # Generate once on startup to ensure dashboard is current
    regenerate()

    observer = Observer()
    observer.schedule(AnalysisFileHandler(), watch_path, recursive=True)
    observer.daemon = True
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
    finally:
        observer.stop()
        observer.join(timeout=5)
        cleanup_pid()


if __name__ == "__main__":
    main()
