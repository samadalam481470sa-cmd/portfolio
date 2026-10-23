"""Small standard-library API for local opportunity exploration."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from estateiq.reports import InvestmentReportGenerator
from estateiq.repository import SQLiteRepository
from estateiq.seed import DEFAULT_DATA_DIR, seed_database
from estateiq.serialization import json_ready


class EstateIQRequestHandler(BaseHTTPRequestHandler):
    """Serve JSON intelligence endpoints and a lightweight map UI."""

    database_path = "estateiq.db"
    static_root = Path(__file__).resolve().parents[2] / "web"

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html", "/map"}:
            self._static_file("index.html")
            return
        if parsed.path.startswith("/assets/"):
            self._static_file(parsed.path.lstrip("/"))
            return
        routes = {
            "/health": self._health,
            "/properties": self._properties,
            "/opportunities": self._opportunities,
            "/map-data": self._map_data,
        }
        if parsed.path.startswith("/properties/") and parsed.path.endswith("/report"):
            self._property_report(parsed.path)
            return
        handler = routes.get(parsed.path)
        if handler is None:
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        handler(parse_qs(parsed.query))

    def _health(self, _query: dict[str, list[str]]) -> None:
        self._json({"status": "ok", "service": "estateiq"})

    def _properties(self, query: dict[str, list[str]]) -> None:
        with _repository(self.database_path) as repository:
            properties = repository.list_properties(
                state=_first(query, "state"),
                city=_first(query, "city"),
            )
        self._json({"properties": json_ready(properties), "count": len(properties)})

    def _opportunities(self, query: dict[str, list[str]]) -> None:
        limit = int(_first(query, "limit") or 25)
        with _repository(self.database_path) as repository:
            opportunities = repository.ranked_opportunities(limit=limit)
        self._json({"opportunities": json_ready(opportunities), "count": len(opportunities)})

    def _map_data(self, query: dict[str, list[str]]) -> None:
        limit = int(_first(query, "limit") or 100)
        with _repository(self.database_path) as repository:
            opportunities = repository.ranked_opportunities(limit=limit)
        features = []
        for opportunity in opportunities:
            property_ = opportunity["property"]
            score = opportunity["score"]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [property_.longitude, property_.latitude],
                    },
                    "properties": {
                        "id": property_.source_id,
                        "address": property_.address,
                        "city": property_.city,
                        "state": property_.state,
                        "price": property_.price,
                        "score": score.score,
                        "recommendation": score.recommendation,
                    },
                }
            )
        self._json({"type": "FeatureCollection", "features": features})

    def _property_report(self, path: str) -> None:
        source_id = path.removeprefix("/properties/").removesuffix("/report")
        with _repository(self.database_path) as repository:
            property_ = repository.get_property(source_id)
            if property_ is None:
                self._json({"error": "property_not_found"}, HTTPStatus.NOT_FOUND)
                return
            market = repository.latest_market_for_zip(property_.zip_code)
            score = repository.get_score(property_.source_id)
            if market is None or score is None:
                self._json({"error": "property_not_scored"}, HTTPStatus.NOT_FOUND)
                return
            contacts = repository.contacts_for_property(property_)
        report = InvestmentReportGenerator().generate(property_, score, market, contacts)
        self._json({"report": json_ready(report)})

    def _static_file(self, relative_path: str) -> None:
        root = self.static_root.resolve()
        requested = (root / relative_path).resolve()
        if not requested.is_relative_to(root) or not requested.is_file():
            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return

        body = requested.read_bytes()
        content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
        if requested.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif requested.suffix in {".css", ".js"}:
            content_type = f"{content_type}; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(json_ready(payload), indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _repository:
    def __init__(self, database_path: str) -> None:
        self.repository = SQLiteRepository(database_path)

    def __enter__(self) -> SQLiteRepository:
        self.repository.initialize_schema()
        return self.repository

    def __exit__(self, *_args: object) -> None:
        self.repository.close()


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def run_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    database_path: str | Path = "estateiq.db",
    seed: bool = False,
) -> None:
    if seed or not Path(database_path).exists():
        seed_database(database_path=database_path, data_dir=DEFAULT_DATA_DIR)
    EstateIQRequestHandler.database_path = str(database_path)
    server = ThreadingHTTPServer((host, port), EstateIQRequestHandler)
    print(f"EstateIQ API listening at http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the EstateIQ local API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--database", default="estateiq.db")
    parser.add_argument("--seed", action="store_true", help="Seed before starting")
    args = parser.parse_args()
    run_server(args.host, args.port, args.database, args.seed)


if __name__ == "__main__":
    main()
