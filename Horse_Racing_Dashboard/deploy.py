"""
Deploy Dashboard — One-click: generate static HTML → commit → push to GitHub.
Netlify auto-deploys from the GitHub repo.

Usage: python deploy.py
"""
import sys, os, io, subprocess, shutil
from pathlib import Path
from datetime import datetime

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DASHBOARD_DIR = Path(__file__).resolve().parent
DEPLOY_DIR = DASHBOARD_DIR / "deploy"
OUTPUT_NAME = "index.html"


def run(cmd, cwd=None):
    """Run a shell command and return output."""
    result = subprocess.run(cmd, shell=True, cwd=cwd or DEPLOY_DIR,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0 and result.stderr:
        print(f"  ⚠️ {result.stderr.strip()}")
    return result


def main():
    # Step 1: Generate static HTML
    print("🏇 Step 1: Generating static dashboard...")
    result = run(f'python3 "{DASHBOARD_DIR / "generate_static.py"}"', cwd=DASHBOARD_DIR)
    if result.returncode != 0:
        print("❌ Generation failed!")
        print(result.stderr)
        return

    source = DASHBOARD_DIR / "Open Dashboard.html"
    if not source.exists():
        print("❌ Open Dashboard.html not found!")
        return

    # Step 2: Copy to deploy folder as index.html
    print("📦 Step 2: Copying to deploy folder...")
    dest = DEPLOY_DIR / OUTPUT_NAME
    shutil.copy2(source, dest)
    size_kb = dest.stat().st_size / 1024
    print(f"   Copied ({size_kb:.0f} KB)")

    # Step 3: Git commit + push
    print("🚀 Step 3: Committing and pushing to GitHub...")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    run("git add -A")
    
    # Check if there are changes to commit
    status = run("git status --porcelain")
    if not status.stdout.strip():
        print("   No changes to deploy — dashboard is already up to date!")
        return

    run(f'git commit -m "Update dashboard {timestamp}"')
    
    # Check if remote exists
    remote_check = run("git remote -v")
    if "origin" not in remote_check.stdout:
        print("\n⚠️  No GitHub remote set up yet!")
        print("   Create a repo on GitHub, then run:")
        print('   cd "' + str(DEPLOY_DIR) + '"')
        print("   git remote add origin https://github.com/YOUR_USERNAME/racing-dashboard.git")
        print("   git branch -M main")
        print("   git push -u origin main")
        print("\n   After that, future deploys will auto-push.")
        return

    push_result = run("git push")
    if push_result.returncode == 0:
        print(f"✅ Deployed! Dashboard will update on Netlify shortly.")
    else:
        print("⚠️  Push failed. You may need to authenticate with GitHub.")
        print("   Try: git push (from the deploy folder)")


if __name__ == "__main__":
    main()
