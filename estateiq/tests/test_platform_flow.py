from __future__ import annotations

import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from estateiq.api import EstateIQRequestHandler
from estateiq.reports import InvestmentReportGenerator
from estateiq.repository import SQLiteRepository
from estateiq.scoring import InvestmentScoringEngine
from estateiq.seed import seed_database


ROOT = Path(__file__).resolve().parents[1]


class PlatformFlowTest(unittest.TestCase):
    def test_root_launcher_is_importable_for_run_button_hosts(self) -> None:
        import main

        self.assertTrue(callable(main.main))

    def test_browser_launcher_is_importable_and_can_find_port(self) -> None:
        import open_website

        self.assertTrue(callable(open_website.main))
        self.assertGreaterEqual(open_website.find_open_port(start=18080, attempts=5), 18080)

    def test_seed_database_collects_and_scores_all_seed_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "estateiq.db"
            counts = seed_database(database, ROOT / "data")

            self.assertEqual(counts["json_listings"], 4)
            self.assertEqual(counts["json_market_snapshots"], 4)
            self.assertEqual(counts["json_public_contacts"], 4)
            self.assertEqual(counts["investment_scores"], 4)

            repository = SQLiteRepository(database)
            try:
                opportunities = repository.ranked_opportunities()
            finally:
                repository.close()

        self.assertEqual(len(opportunities), 4)
        scores = [opportunity["score"].score for opportunity in opportunities]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_scoring_prefers_discounted_property_in_strong_market(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "estateiq.db"
            seed_database(database, ROOT / "data")
            repository = SQLiteRepository(database)
            try:
                property_ = repository.get_property("builder-nc-771")
                self.assertIsNotNone(property_)
                market = repository.latest_market_for_zip(property_.zip_code)  # type: ignore[union-attr]
                self.assertIsNotNone(market)
                score = InvestmentScoringEngine().score_property(property_, market)  # type: ignore[arg-type]
            finally:
                repository.close()

        self.assertGreaterEqual(score.market_strength, 75)
        self.assertIn(score.recommendation, {"Priority target", "Strong watchlist"})
        self.assertTrue(score.reasons)

    def test_report_contains_contacts_and_underwriting_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "estateiq.db"
            seed_database(database, ROOT / "data")
            repository = SQLiteRepository(database)
            try:
                property_ = repository.get_property("mls-atl-1001")
                self.assertIsNotNone(property_)
                score = repository.get_score(property_.source_id)  # type: ignore[union-attr]
                market = repository.latest_market_for_zip(property_.zip_code)  # type: ignore[union-attr]
                contacts = repository.contacts_for_property(property_)  # type: ignore[arg-type]
                report = InvestmentReportGenerator().generate(property_, score, market, contacts)  # type: ignore[arg-type]
            finally:
                repository.close()

        self.assertIn("214 Maple Bend Dr", report.title)
        self.assertIn("Validate rent estimate", " ".join(report.next_steps))
        self.assertTrue(any("Avery Jackson" in step for step in report.next_steps))

    def test_website_serves_homepage_assets_and_api_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "estateiq.db"
            seed_database(database, ROOT / "data")
            EstateIQRequestHandler.database_path = str(database)
            server = ThreadingHTTPServer(("127.0.0.1", 0), EstateIQRequestHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            base_url = f"http://{host}:{port}"
            try:
                homepage = urlopen(f"{base_url}/", timeout=5).read().decode("utf-8")
                script = urlopen(f"{base_url}/assets/app.js", timeout=5).read().decode("utf-8")
                opportunities = urlopen(f"{base_url}/opportunities", timeout=5).read().decode("utf-8")
            finally:
                server.shutdown()
                server.server_close()

        self.assertIn("EstateIQ | Real Estate Intelligence", homepage)
        self.assertIn("loadDashboard", script)
        self.assertIn("opportunities", opportunities)

    def test_static_website_can_open_without_server_paths(self) -> None:
        homepage = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        demo_data = (ROOT / "web" / "assets" / "demo-data.js").read_text(encoding="utf-8")
        app = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('href="assets/styles.css"', homepage)
        self.assertIn('src="assets/demo-data.js"', homepage)
        self.assertIn("window.ESTATEIQ_DEMO_DATA", demo_data)
        self.assertIn("fallbackReport", app)

    def test_gitlab_pages_pipeline_publishes_static_site(self) -> None:
        pipeline = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")

        self.assertIn("pages:", pipeline)
        self.assertIn("cp -R web/* public/", pipeline)
        self.assertIn("- public", pipeline)


if __name__ == "__main__":
    unittest.main()
