"""Watch the configured analysis root for new or modified reports."""
import time
import threading
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import config

logger = logging.getLogger(__name__)


class AnalysisFileHandler(FileSystemEventHandler):
    """Watch analysis plus racecard metadata consumed by the test API."""
    
    def __init__(self, on_change_callback):
        super().__init__()
        self.on_change = on_change_callback
        self._last_trigger = 0
        self._debounce_seconds = 3  # Avoid rapid-fire refreshes
    
    def _should_handle(self, path: str) -> bool:
        """Handle every source that can change races or runner display data."""
        p = Path(path)
        if p.name.startswith('.') or p.suffix not in ('.txt', '.md', '.json'):
            return False
        return any(
            marker in p.name
            for marker in (
                'Analysis',
                'Racecard',
                '排位表',
                '全日出賽馬匹資料',
                'MC_Results',
            )
        )
    
    def _debounced_trigger(self):
        now = time.time()
        if now - self._last_trigger > self._debounce_seconds:
            self._last_trigger = now
            logger.info(f"Analysis file change detected, invalidating cache")
            self.on_change()
    
    def on_created(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            self._debounced_trigger()
    
    def on_modified(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            self._debounced_trigger()


class FileWatcher:
    """Watches Antigravity root directory for analysis file changes."""
    
    def __init__(self, on_change_callback):
        self.observer = Observer()
        self.handler = AnalysisFileHandler(on_change_callback)
        # More than one root once AU lives on local disk and HK stays on Drive.
        self.watch_paths = [str(p) for p in config.WATCH_ROOTS]
        self.watch_path = self.watch_paths[0]  # kept for the status payload shape
        self._running = False
        self.last_updated = time.time()
        self._original_callback = on_change_callback
    
    def _on_change(self):
        """Wrapper that updates timestamp and calls the callback."""
        self.last_updated = time.time()
        self._original_callback()
    
    def start(self):
        """Start watching in a background thread."""
        if self._running:
            return
        
        # Re-wire handler to use our wrapper
        self.handler.on_change = self._on_change
        
        scheduled = []
        for path in self.watch_paths:
            try:
                self.observer.schedule(self.handler, path, recursive=True)
                scheduled.append(path)
            except Exception as e:
                # One unreachable root (an unmounted Drive) must not cost us the
                # others — the local AU root is the one that changes daily.
                logger.error(f"Failed to watch {path}: {e}")
        if not scheduled:
            logger.error("File watcher started no roots; dashboard will not auto-refresh")
            return
        try:
            self.observer.daemon = True
            self.observer.start()
            self._running = True
            logger.info(f"File watcher started on {', '.join(scheduled)}")
        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")
    
    def stop(self):
        """Stop watching."""
        if self._running:
            self.observer.stop()
            self.observer.join(timeout=5)
            self._running = False
            logger.info("File watcher stopped")
    
    def get_status(self) -> dict:
        """Return current watcher status."""
        return {
            "watching": self._running,
            "watch_path": self.watch_path,
            "watch_paths": self.watch_paths,
            "last_updated": self.last_updated,
        }
