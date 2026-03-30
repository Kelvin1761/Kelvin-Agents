import sys
import os
import subprocess
import time

def start_lightpanda(base_dir):
    """
    Pre-flight Environment Scan (Wong Choi / Reflector Dual-track mechanism)
    Detects OS, checks for WSL on Windows, and spawns the correct Lightpanda server.
    Returns: (use_lightpanda: bool, process_handler: subprocess.Popen)
    """
    print("\n[Pre-flight] Checking environment for Lightpanda Browser...")
    try:
        if sys.platform == 'darwin':
            # Mac environment (Apple Silicon assumed)
            exec_path = os.path.join(base_dir, "lightpanda-mac")
            if not os.path.exists(exec_path):
                print(f"  [WARN] Mac executable missing at {exec_path}. Falling back to Chromium.")
                return False, None
            
            print("  ✓ Detected Mac OS. Spawning native Lightpanda...")
            # We use DEVNULL to avoid filling up the buffer with logs
            proc = subprocess.Popen([exec_path, "serve", "--host", "127.0.0.1", "--port", "9222"], 
                                    cwd=base_dir,
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.DEVNULL)
            time.sleep(2) # Allow server to bind
            return True, proc
            
        elif sys.platform == 'win32':
            # Windows environment (Heison's machine)
            print("  ✓ Detected Windows OS. Checking for WSL (Windows Subsystem for Linux)...")
            
            # 1. Check if WSL is available
            wsl_check = subprocess.run(["wsl", "-e", "echo", "1"], capture_output=True, text=True)
            if wsl_check.returncode != 0:
                print("  [WARN] WSL is not installed or enabled on this Windows machine.")
                print("         (If you want faster extraction, run 'wsl --install' as admin and restart.)")
                print("  [WARN] Falling back to default Chromium Playwright.")
                return False, None
            
            # 2. Check if the Linux executable exists
            exec_path = os.path.join(base_dir, "lightpanda-linux")
            if not os.path.exists(exec_path):
                 print(f"  [WARN] Linux executable missing at {exec_path}. Falling back to Chromium.")
                 return False, None

            print("  ✓ WSL enabled. Spawning Lightpanda (Linux version) via WSL...")
            # WSL automatically translates the Windows cwd to the Linux equivalent (/mnt/...)
            proc = subprocess.Popen(
                ["wsl", "./lightpanda-linux", "serve", "--host", "127.0.0.1", "--port", "9222"],
                cwd=base_dir,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            time.sleep(3) # wsl initialization usually takes a tiny bit longer
            return True, proc
            
        else:
            print(f"  [WARN] OS {sys.platform} not explicitly handled for Lightpanda. Falling back.")
            return False, None
            
    except Exception as e:
        print(f"  [WARN] Lightpanda pre-flight failed: {e}. Falling back to Chromium.")
        return False, None

def stop_lightpanda(proc):
    """Gracefully termiantes the background Lightpanda process."""
    if proc:
        print("\n[Pre-flight] Terminating Lightpanda background server...")
        try:
            if sys.platform == 'win32':
                # On Windows, terminating 'wsl' might leave the Linux backend process orphaned
                # A safer approach is to ask wsl to kill the specific port or process
                subprocess.run(["wsl", "pkill", "-f", "lightpanda-linux"], capture_output=True)
            
            proc.terminate()
            proc.wait(timeout=2)
        except:
            proc.kill()
