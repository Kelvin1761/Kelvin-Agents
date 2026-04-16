#!/usr/bin/env python3
"""
claw_bet365_receiver.py — Local HTTP Server for Tampermonkey Data Ingestion (V2)

Receives JSON data POSTed by bet365_tampermonkey.js and saves:
1. Raw combined JSON: bet365_all_raw_data.json
2. Per-game split JSON: Bet365_Odds_{GAME_TAG}.json (parsed by bet365_parser.py)

Usage:
  python3 claw_bet365_receiver.py [--output-dir /path/to/target]
  
Then open Bet365 in Comet and click the green "EXTRACT" button.

Version: 2.0.0
"""
import sys
import os
import json
import argparse
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Default output directory
DEFAULT_OUTPUT_DIR = "/tmp"


class RequestHandler(BaseHTTPRequestHandler):
    output_dir = DEFAULT_OUTPUT_DIR

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == '/ingest':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')

            try:
                data = json.loads(post_data)
                
                # Save raw combined data
                raw_path = os.path.join(self.output_dir, "bet365_all_raw_data.json")
                with open(raw_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                tabs = data.get("tabs", data.get("props_raw", {}))
                game_tags = data.get("game_tags", [])
                source = data.get("source", "Unknown")
                
                print(f"\n{'='*55}")
                print(f"✅ SUCCESS: Received data from {source}")
                print(f"{'='*55}")
                print(f"📂 Output directory: {self.output_dir}")
                print(f"💾 Raw data saved: {raw_path}")
                print(f"")
                
                for tab_name, tab_data in tabs.items():
                    lines = len(tab_data) if isinstance(tab_data, list) else 0
                    status = "✅" if lines >= 10 else ("⚠️" if lines > 0 else "❌")
                    print(f"  {status} {tab_name}: {lines} lines")
                
                if game_tags:
                    print(f"\n🏷️ Game Tags: {', '.join(game_tags)}")
                
                print(f"\n🎯 下一步: 執行 bet365_parser.py 將 raw data 拆分為 per-game JSON")
                print(f"{'='*55}")

                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "saved": raw_path}).encode())

            except Exception as e:
                print(f"[!] Error processing JSON: {e}")
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def run_server(port=8888, output_dir=DEFAULT_OUTPUT_DIR):
    RequestHandler.output_dir = output_dir
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    
    print("=" * 55)
    print("  🏀 NBA WONG CHOI — Tampermonkey Receiver V2")
    print("=" * 55)
    print(f"  📡 Listening: http://localhost:{port}/ingest")
    print(f"  📂 Output:    {output_dir}")
    print(f"")
    print(f"  📋 Instructions:")
    print(f"  1. Open bet365.com.au in Comet browser")
    print(f"  2. Navigate to NBA section")
    print(f"  3. Click the green '🏀 EXTRACT NBA' button")
    print(f"  4. Wait for extraction to complete (~20 seconds)")
    print(f"  5. This server will save the data automatically")
    print(f"")
    print(f"  ⏳ Waiting for data...")
    print("=" * 55)

    try:
        httpd.serve_forever()
    except (SystemExit, KeyboardInterrupt):
        print("\n[Server] Shutting down.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Bet365 Tampermonkey Receiver V2')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR,
                        help='Directory to save output JSON files')
    parser.add_argument('--port', type=int, default=8888,
                        help='Server port (default: 8888)')
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    run_server(port=args.port, output_dir=args.output_dir)
