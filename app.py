"""
app.py
======
Production-ready web application & REST API for the Payments Reconciliation Platform.
Can be hosted locally or deployed on Render (uses PORT environment variable).

Endpoints:
- GET  /                        : Interactive Dashboard UI
- GET  /health                  : Health check (Render / uptime monitoring)
- POST /api/reconcile           : Upload & reconcile two CSV files
- POST /api/reconcile-sample    : Load built-in sample data and reconcile
- POST /api/benchmark           : Evaluate framework against ground_truth.csv
- GET  /api/export              : Download reconciled report as CSV
"""

import os
import sys
import json
import socket
import math
import email
from datetime import datetime, date
from email.policy import default
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

import pandas as pd
import numpy as np

from reconciliation_engine import ReconciliationEngine

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SAMPLE_PLATFORM_CSV = BASE_DIR / "platform_transactions.csv"
SAMPLE_BANK_CSV = BASE_DIR / "bank_transactions.csv"
SAMPLE_GROUND_TRUTH_CSV = BASE_DIR / "ground_truth.csv"

# In-memory cache for latest reconciliation result (for instant export / benchmark)
LATEST_RECON_CACHE = {
    "result": None,
    "platform_filename": "platform_transactions.csv",
    "bank_filename": "bank_transactions.csv"
}

engine = ReconciliationEngine()

def sanitize_for_json(obj):
    """
    Recursively sanitize objects for standard JSON serialization.
    Replaces NaN, Inf, and -Inf with None (which json.dumps encodes as null).
    Serializes datetime, date, and pd.Timestamp into ISO string format.
    """
    if obj is None:
        return None
    if isinstance(obj, (datetime, date, pd.Timestamp)):
        return str(obj)
    if isinstance(obj, (np.floating, float)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(v) for v in obj]
    if pd.isna(obj):
        return None
    return obj

def get_part_text(part):
    """Safely extract decoded text from an email multipart component."""
    if part is None:
        return None
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
    except Exception:
        pass

    try:
        payload = part.get_payload(decode=True)
        if payload is not None:
            if isinstance(payload, bytes):
                return payload.decode("utf-8", errors="replace")
            return str(payload)
    except Exception:
        pass

    try:
        raw = part.get_payload()
        if isinstance(raw, str):
            return raw
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
    except Exception:
        pass
    return None

class ReconciliationHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json(200, {
                "status": "healthy",
                "service": "payments-reconciliation-platform",
                "version": "1.0.0"
            })
            return

        if path == "/api/export":
            self._handle_export()
            return

        if path in ("", "/"):
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                self._send_file(index_path, "text/html; charset=utf-8")
                return

        # Serve static assets
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/reconcile-sample":
            self._handle_reconcile_sample()
            return

        if path == "/api/reconcile":
            self._handle_reconcile_upload()
            return

        if path == "/api/benchmark":
            self._handle_benchmark()
            return

        if path == "/api/export":
            self._handle_export()
            return

        self._send_json(404, {"error": f"Endpoint not found: {path}"})

    # -------------------------------------------------------------
    # Request Handlers
    # -------------------------------------------------------------
    def _handle_reconcile_sample(self):
        try:
            if not SAMPLE_PLATFORM_CSV.exists() or not SAMPLE_BANK_CSV.exists():
                self._send_json(404, {"error": "Sample data files not found on server."})
                return

            result = engine.reconcile(str(SAMPLE_PLATFORM_CSV), str(SAMPLE_BANK_CSV))
            LATEST_RECON_CACHE["result"] = result
            LATEST_RECON_CACHE["platform_filename"] = "platform_transactions.csv"
            LATEST_RECON_CACHE["bank_filename"] = "bank_transactions.csv"

            self._send_json(200, {
                "success": True,
                "message": "Sample transactions successfully reconciled.",
                "data": result
            })
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

    def _handle_reconcile_upload(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)

            platform_csv = None
            bank_csv = None
            p_name = "uploaded_platform.csv"
            b_name = "uploaded_bank.csv"

            if "multipart/form-data" in content_type:
                headers = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
                msg = email.message_from_bytes(headers + body_bytes, policy=default)

                if msg.is_multipart():
                    for part in msg.iter_parts():
                        name = part.get_param("name", header="content-disposition")
                        filename = part.get_filename()
                        if name in ("platform_file", "platform_csv"):
                            platform_csv = get_part_text(part)
                            if filename:
                                p_name = filename
                        elif name in ("bank_file", "bank_csv"):
                            bank_csv = get_part_text(part)
                            if filename:
                                b_name = filename
            elif "application/json" in content_type:
                payload = json.loads(body_bytes.decode("utf-8", errors="replace"))
                platform_csv = payload.get("platform_csv")
                bank_csv = payload.get("bank_csv")
                p_name = payload.get("platform_filename", p_name)
                b_name = payload.get("bank_filename", b_name)

            if not platform_csv or not bank_csv:
                self._send_json(400, {
                    "success": False,
                    "error": "Both 'platform_file' and 'bank_file' CSV inputs are required."
                })
                return

            result = engine.reconcile(platform_csv, bank_csv)
            LATEST_RECON_CACHE["result"] = result
            LATEST_RECON_CACHE["platform_filename"] = p_name
            LATEST_RECON_CACHE["bank_filename"] = b_name

            self._send_json(200, {
                "success": True,
                "message": "Uploaded files successfully reconciled.",
                "data": result
            })
        except Exception as e:
            self._send_json(500, {"success": False, "error": f"Reconciliation failed: {str(e)}"})

    def _handle_benchmark(self):
        try:
            recon_res = LATEST_RECON_CACHE["result"]
            if not recon_res:
                # Run sample recon if not already run
                if not SAMPLE_PLATFORM_CSV.exists() or not SAMPLE_BANK_CSV.exists():
                    self._send_json(404, {"error": "Sample data not found."})
                    return
                recon_res = engine.reconcile(str(SAMPLE_PLATFORM_CSV), str(SAMPLE_BANK_CSV))
                LATEST_RECON_CACHE["result"] = recon_res

            if not SAMPLE_GROUND_TRUTH_CSV.exists():
                self._send_json(404, {"error": "ground_truth.csv not found for benchmarking."})
                return

            eval_res = engine.evaluate_against_ground_truth(str(SAMPLE_GROUND_TRUTH_CSV), recon_res)
            self._send_json(200, {
                "success": True,
                "benchmark": eval_res
            })
        except Exception as e:
            self._send_json(500, {"success": False, "error": f"Benchmark failed: {str(e)}"})

    def _handle_export(self):
        try:
            recon_res = LATEST_RECON_CACHE["result"]
            if not recon_res:
                if SAMPLE_PLATFORM_CSV.exists() and SAMPLE_BANK_CSV.exists():
                    recon_res = engine.reconcile(str(SAMPLE_PLATFORM_CSV), str(SAMPLE_BANK_CSV))
                    LATEST_RECON_CACHE["result"] = recon_res
                else:
                    self._send_json(400, {"error": "No reconciliation results to export. Run reconciliation first."})
                    return

            csv_data = engine.export_to_csv(recon_res)
            csv_bytes = csv_data.encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="reconciliation_report.csv"')
            self.send_header("Content-Length", str(len(csv_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(csv_bytes)
        except Exception as e:
            self._send_json(500, {"error": f"Export failed: {str(e)}"})

    # -------------------------------------------------------------
    # Response Utilities
    # -------------------------------------------------------------
    def _send_json(self, status_code, data):
        clean_data = sanitize_for_json(data)
        body = json.dumps(clean_data, indent=2, allow_nan=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath, content_type):
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def create_server(host, port, handler_cls):
    """
    Create a multi-threaded HTTP server.
    Uses Dual-Stack (IPv6 + IPv4) if available so both http://localhost:<port>
    (which may resolve to ::1 on Windows) and http://127.0.0.1:<port> work seamlessly.
    """
    if host in ("0.0.0.0", "", "::") and hasattr(socket, "has_dualstack_ipv6") and socket.has_dualstack_ipv6():
        try:
            class DualStackServer(ThreadingHTTPServer):
                address_family = socket.AF_INET6
                allow_reuse_address = True

                def server_bind(self):
                    self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                    return super().server_bind()

            return DualStackServer(("::", port), handler_cls)
        except Exception:
            pass

    class IPv4Server(ThreadingHTTPServer):
        allow_reuse_address = True

    return IPv4Server((host, port), handler_cls)

def run_server(host="0.0.0.0", port=None, open_browser=True):
    if port is None:
        port = int(os.environ.get("PORT", 8000))

    try:
        httpd = create_server(host, port, ReconciliationHandler)
    except OSError as e:
        if "10048" in str(e) or "already in use" in str(e).lower():
            print(f"⚠️ Port {port} is currently in use. Trying port {port + 1}...")
            port = port + 1
            httpd = create_server(host, port, ReconciliationHandler)
        else:
            raise

    local_url = f"http://localhost:{port}"
    ipv4_url = f"http://127.0.0.1:{port}"

    print("=" * 70)
    print("🚀 FinRecon Payments Reconciliation Platform is RUNNING!")
    print("=" * 70)
    print(f"👉 OPEN IN BROWSER:   {local_url}")
    print(f"👉 ALTERNATIVE URL:   {ipv4_url}")
    print(f"🩺 HEALTH CHECK:      {local_url}/health")
    print(f"📁 SERVING STATIC UI: {STATIC_DIR}")
    print("-" * 70)
    print("💡 NOTE FOR WINDOWS:")
    print("   Do NOT navigate to 'http://0.0.0.0:8000' in Chrome/Edge (Windows will reject it).")
    print(f"   Use '{local_url}' or '{ipv4_url}' instead.")
    print("=" * 70)
    print("Press Ctrl+C to stop the server.\n")

    # Optionally auto-open the browser in local interactive runs
    if open_browser and not os.environ.get("RENDER") and not os.environ.get("CI"):
        try:
            import webbrowser
            import threading
            threading.Timer(0.6, lambda: webbrowser.open(local_url)).start()
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FinRecon server...")
        httpd.server_close()

if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    run_server(port=port_arg)
