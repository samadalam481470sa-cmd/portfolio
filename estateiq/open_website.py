"""Start EstateIQ locally and open it in your browser.

This is the easiest launcher for Safari/localhost usage:

    python3 open_website.py

Keep the terminal window open while using the website. Press Ctrl+C to stop it.
"""

from __future__ import annotations

import os
import socket
import sys
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from estateiq.api import EstateIQRequestHandler  # noqa: E402
from estateiq.seed import seed_database  # noqa: E402


def find_open_port(start: int = 8080, attempts: int = 50) -> int:
    """Find an available localhost port, starting with the expected web port."""

    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No open port found from {start} to {start + attempts - 1}")


def main() -> None:
    """Seed demo data, start the local server, and open the browser."""

    port = int(os.environ.get("PORT") or find_open_port())
    database_path = os.environ.get("ESTATEIQ_DATABASE", "estateiq.db")
    seed_database(database_path=database_path, data_dir=ROOT / "data")

    EstateIQRequestHandler.database_path = database_path
    server = ThreadingHTTPServer(("127.0.0.1", port), EstateIQRequestHandler)
    url = f"http://localhost:{port}/"
    print(f"EstateIQ is running at {url}")
    print("Keep this terminal open. Press Ctrl+C to stop the website.")

    if os.environ.get("ESTATEIQ_NO_BROWSER") != "1":
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping EstateIQ.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
