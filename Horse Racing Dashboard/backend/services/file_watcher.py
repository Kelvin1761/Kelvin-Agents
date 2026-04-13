"""
File Watcher — Monitors Antigravity root for new/modified analysis files.
Invalidates the meetings cache when changes are detected.
"""
import time
import threading
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import config

logger = logging.getLogger(__name__)


class AnalysisFileHandler(FileSystemEventHandler):
    """Watches for *Analysis.txt file changes."""
    
    def __init__(self, on_change_callback):
        super().__init__()
        self.on_change = on_change_callback
        self._last_trigger = 0
        self._debounce_seconds = 3  # Avoid rapid-fire refreshes
    
    def _should_handle(self, path: str) -> bool:
        """Only handle analysis files."""
        p = Path(path)
        return (
            p.suffix in ('.txt', '.md') and 
            'Analysis' in p.name and
            not p.name.startswith('.')
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
        self.watch_path = str(config.ANTIGRAVITY_ROOT)
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
        
        try:
            self.observer.schedule(
                self.handler, 
                self.watch_path, 
                recursive=True
            )
            self.observer.daemon = True
            self.observer.start()
            self._running = True
            logger.info(f"File watcher started on {self.watch_path}")
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
            "last_updated": self.last_updated,
        }
