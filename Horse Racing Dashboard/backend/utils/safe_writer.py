import os
import signal
import subprocess
import tempfile
import time

class WriteTimeoutError(Exception):
    pass

def _timeout_handler(signum, frame):
    raise WriteTimeoutError(f"File write timed out after signal {signum}")

def safe_write(target_path: str, content: str, encoding: str = 'utf-8', mode: str = 'w',
               timeout: int = 120, retries: int = 2, retry_delay: int = 5) -> str:
    """
    Safe file writer with timeout + retry. Zero external dependencies.
    Attempt 1: Direct write with 120s timeout
    Attempt 2+ (retry): Write to /tmp first, then cp/cat to target
    """
    if mode not in ('w', 'a'):
        raise ValueError("Mode must be 'w' or 'a'")
        
    for attempt in range(retries + 1):
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            try:
                os.makedirs(os.path.dirname(target_path) or '.', exist_ok=True)
                with open(target_path, mode, encoding=encoding) as f:
                    f.write(content)
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                return target_path
            except WriteTimeoutError:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
                # Fallback: write to /tmp then move/append
                basename = os.path.basename(target_path)
                tmp_path = os.path.join(tempfile.gettempdir(), f"_sfw_{basename}")
                with open(tmp_path, 'w', encoding=encoding) as f:
                    f.write(content)
                
                if mode == 'a':
                    # Append using cat
                    subprocess.run(f'cat "{tmp_path}" >> "{target_path}"', shell=True, check=True, timeout=30)
                else:
                    # Write using cp
                    subprocess.run(['cp', tmp_path, target_path], check=True, timeout=30)
                
                os.remove(tmp_path)
                return target_path
        except Exception as e:
            if attempt < retries:
                time.sleep(retry_delay)
                continue
            raise
    return target_path
