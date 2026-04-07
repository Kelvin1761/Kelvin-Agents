import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
from pathlib import Path

# Disable logging to keep console clean
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

SCRIPT_DIR = Path(__file__).parent
OUTPUT_FILE = SCRIPT_DIR / "bet365_extracted_raw.json"

class RequestHandler(BaseHTTPRequestHandler):
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
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                print(f"\n[+] SUCCESS: Received Bet365 Data from Browser Plugin!")
                print(f"[+] Saved {len(data.get('games_raw', []))} Game Lines to {OUTPUT_FILE.name}")
                
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b"OK")
                
                # Exit the server gracefully after successful ingestion
                sys.exit(0)
            except Exception as e:
                print(f"[!] Error processing JSON: {e}")
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass # Suppress default HTTP server logging

def run_server(port=8888):
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print("====================================")
    print("   NBA WONG CHOI - WEBHCOK RECEIVER")
    print("====================================")
    print(f"[*] Listening on http://localhost:{port}/ingest")
    print("[*] Waiting for Tampermonkey extension to send data...")
    print("[*] Please open the NBA section in your normal Comet browser.")
    
    try:
        httpd.serve_forever()
    except SystemExit:
        pass # Normal exit

if __name__ == "__main__":
    run_server()
