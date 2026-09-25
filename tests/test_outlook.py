"""전망 제품의 날짜/근거/저장 경계. 합성 관측만 사용하고 운영 DB는 호출하지 않는다."""
import calendar
import re
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from outlook.app import create_app
from outlook.evidence import build_evidence, read_observations
from outlook.store import SnapshotStore
from scripts import security_source_gate

CUTOFF = date(2026, 9, 23)


def daily(year=2026, month=8, value=100, **overrides):
    rows = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        row = {
            "metric": "gas_production", "period": date(year, month, day),
            "value": value, "unit": "Bcf/d", "source": "Platts",
            "fetched_at": datetime(2026, 9, 20),
        }
        row.update(overrides)
        rows.append(row)
    return rows


class ObservationTests(unittest.TestCase):
    def test_cutoff_filters_observation_and_collection_dates(self):
        rows = daily() + daily(year=2025, value=90)
        rows += daily(month=10, value=200)
        rows += daily(month=7, value=300, fetched_at=datetime(2026, 9, 24))
        evidence = build_evidence(CUTOFF, rows)
        metric = evidence["metrics"]["gas_production"]
        self.assertEqual(metric["latest"]["month"], "2026-08-01")
        self.assertEqual(metric["latest"]["value"], 100)
        self.assertEqual(metric["change"], 10)
        self.assertEqual(len(metric["points"]), 2)
        self.assertEqual(build_evidence(date(2025, 9, 1), rows)["status"], "empty")

    def test_current_and_sparse_months_do_not_masquerade_as_complete(self):
        evidence = build_evidence(CUTOFF, daily(month=9) + daily(month=8)[:15] + daily(month=7))
        metric = evidence["metrics"]["gas_production"]
        self.assertEqual(metric["latest"]["month"], "2026-07-01")
        self.assertTrue(metric["stale"])
        self.assertEqual(metric["excluded"], 15)

    def test_alternate_sources_bad_units_and_nonfinite_values_are_not_mixed(self):
        rows = daily() + daily(value=500, source="Other")
        rows += daily(month=7, unit="MMcf/d") + daily(month=6, value=float("nan"))
        metric = build_evidence(CUTOFF, rows)["metrics"]["gas_production"]
        self.assertEqual(metric["latest"]["value"], 100)
        self.assertEqual(len(metric["points"]), 1)
        self.assertEqual(metric["excluded"], 61)

    def test_duplicate_observation_uses_latest_collection_once(self):
        revised = daily(value=110, fetched_at=datetime(2026, 9, 21))
        metric = build_evidence(CUTOFF, revised + daily())["metrics"]["gas_production"]
        self.assertEqual(metric["latest"]["value"], 110)
        self.assertEqual(metric["latest"]["observations"], 31)

    def test_weekly_stocks_use_last_value_not_a_sum_or_average(self):
        rows = [{"metric": "gas_storage", "source": "EIA", "unit": "Bcf",
                 "period": date(2026, 8, day), "value": value,
                 "fetched_at": datetime(2026, 9, 20)}
                for day, value in [(7, 2800), (14, 2900), (21, 3000), (28, 3100)]]
        metric = build_evidence(CUTOFF, rows)["metrics"]["gas_storage"]
        self.assertEqual(metric["latest"]["value"], 3100)
        self.assertEqual(metric["latest"]["last_observation"], "2026-08-28")

    def test_monthly_weather_remains_monthly_and_zero_reference_is_valid(self):
        rows = [{"metric": "hdd_tx", "source": "NOAA", "unit": "HDD",
                 "period": date(year, 8, 1), "value": value,
                 "fetched_at": datetime(2026, 9, 20)} for year, value in [(2025, 0), (2026, 2)]]
        metric = build_evidence(CUTOFF, rows)["metrics"]["hdd_tx"]
        self.assertEqual(metric["change"], 2)
        self.assertEqual(metric["latest"]["observations"], 1)

    def test_chart_does_not_connect_missing_months(self):
        metric = build_evidence(CUTOFF, daily(month=5) + daily(month=8))["metrics"]["gas_production"]
        self.assertEqual(len(metric["chart"]["segments"]), 2)
        self.assertIsNone(metric["change"])

    def test_historical_empty_and_connection_error_are_distinct(self):
        self.assertEqual(build_evidence(date(1980, 1, 1), [])["status"], "empty")
        self.assertEqual(build_evidence(CUTOFF, [], error=True)["status"], "unavailable")

    def test_reader_uses_shared_db_and_bound_cutoff(self):
        cursor = MagicMock()
        cursor.description = [(column,) for column in ("metric", "period", "value", "unit", "source", "fetched_at")]
        cursor.fetchall.return_value = []
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with patch("outlook.evidence.db.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            self.assertEqual(read_observations(CUTOFF), [])
        sql, params = cursor.execute.call_args.args
        self.assertIn("fetched_at < %(available_before)s", sql)
        self.assertEqual(params["available_before"], date(2026, 9, 24))
        self.assertEqual(params["cutoff"], CUTOFF)
        self.assertNotIn("2026-09-23", sql)


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.reader = MagicMock(return_value=daily())
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "test-only-key",
            "SNAPSHOT_DIR": Path(self.temp.name), "OBSERVATION_READER": self.reader,
            "TODAY": lambda: CUTOFF,
        })
        self.client = self.app.test_client()

    def draft(self, client=None, query=""):
        client = client or self.client
        response = client.get("/perspectives" + query)
        html = response.get_data(as_text=True)
        return {
            "csrf": re.search(r'name="csrf" value="([^"]+)"', html).group(1),
            "draft_id": re.search(r'name="draft_id" value="([^"]+)"', html).group(1),
            "name": "Autumn research", "axes": ["supply", "policy"], "note": "Watch permits.",
        }

    def test_real_template_and_security_headers(self):
        response = self.client.get("/perspectives")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("100", html)
        self.assertIn("Bcf/d", html)
        self.assertIn("Not yet validated", html)
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", response.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/perspectives", base_url="http://evil.example").status_code, 400)

    def test_future_invalid_and_unknown_axis_are_rejected(self):
        for query in ("?as_of=2026-09-24", "?as_of=bad", "?as_of=1970-01-01"):
            self.assertEqual(self.client.get("/perspectives" + query).status_code, 400)
        self.assertEqual(self.client.get("/perspectives?axis=unknown").status_code, 404)

    def test_cache_avoids_repeated_db_queries_when_switching_axes(self):
        self.client.get("/perspectives")
        self.client.get("/perspectives?axis=lng")
        self.reader.assert_called_once_with(CUTOFF)

    def test_save_freezes_displayed_observations_and_reopen_never_queries_db(self):
        form = self.draft()
        self.reader.return_value = daily(value=999)
        response = self.client.post("/perspectives/save", data=form)
        self.assertEqual(response.status_code, 303)
        self.reader.reset_mock()
        view = self.client.get(response.location)
        self.assertEqual(view.status_code, 200)
        self.assertIn("Frozen perspective", view.get_data(as_text=True))
        self.reader.assert_not_called()
        stored = SnapshotStore(Path(self.temp.name)).get(response.location.rsplit("/", 1)[1])
        self.assertEqual(stored["evidence"]["metrics"]["gas_production"]["latest"]["value"], 100)
        self.assertEqual(stored["selected_axes"], ["supply", "policy"])

    def test_snapshot_survives_app_restart(self):
        response = self.client.post("/perspectives/save", data=self.draft())
        restarted = create_app({"TESTING": True, "SNAPSHOT_DIR": Path(self.temp.name), "OBSERVATION_READER": self.reader})
        self.reader.reset_mock()
        self.assertEqual(restarted.test_client().get(response.location).status_code, 200)
        self.reader.assert_not_called()

    def test_csrf_session_ownership_and_expiry(self):
        form = self.draft()
        self.assertEqual(self.client.post("/perspectives/save", data={**form, "csrf": "wrong"}).status_code, 400)
        self.assertEqual(self.client.post("/perspectives/save", data={**form, "csrf": "잘못된 토큰"}).status_code, 400)
        second = self.app.test_client()
        second_form = self.draft(second)
        self.assertEqual(second.post("/perspectives/save", data={**form, "csrf": second_form["csrf"]}).status_code, 400)
        with patch("outlook.app.monotonic", return_value=10**15):
            self.assertEqual(self.client.post("/perspectives/save", data=form).status_code, 400)
        self.assertEqual(list(Path(self.temp.name).glob("*.json")), [])

    def test_invalid_selection_and_overlong_notes_do_not_save(self):
        form = self.draft()
        for changes in ({"axes": []}, {"axes": ["unknown"]}, {"name": " "}, {"note": "a" * 3001}):
            self.assertEqual(self.client.post("/perspectives/save", data={**form, **changes}).status_code, 400)
        self.assertEqual(list(Path(self.temp.name).glob("*.json")), [])

    def test_notes_and_name_are_escaped(self):
        form = self.draft()
        response = self.client.post("/perspectives/save", data={**form, "name": '<script>alert(1)</script>', "note": '<img src=x onerror="alert(1)">'}, follow_redirects=True)
        html = response.get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)

    def test_error_does_not_expose_connection_secret_or_enable_save(self):
        self.reader.side_effect = RuntimeError("password=private-canary")
        form = self.draft()
        response = self.client.get("/perspectives")
        self.assertIn("Observations could not be loaded", response.get_data(as_text=True))
        self.assertNotIn("private-canary", response.get_data(as_text=True))
        self.assertEqual(self.client.post("/perspectives/save", data=form).status_code, 400)

    def test_historical_cutoff_does_not_invent_period_axes(self):
        response = self.client.get("/perspectives?as_of=1980-01-01")
        html = response.get_data(as_text=True)
        self.assertIn("No usable observations at this cutoff", html)
        self.assertIn("not a reconstruction of the axes of that era", html)

    def test_traversal_and_unreadable_snapshot_are_handled(self):
        store = SnapshotStore(Path(self.temp.name))
        with self.assertRaises(ValueError):
            store.get("../../config")
        self.assertEqual(self.client.get("/perspectives/saved/bad").status_code, 404)
        (Path(self.temp.name) / ("a" * 32 + ".json")).write_text("broken", encoding="utf-8")
        self.assertEqual(self.client.get("/perspectives/saved/" + "a" * 32).status_code, 404)
        self.assertIn("could not be read", self.client.get("/perspectives").get_data(as_text=True))

    def test_outlook_sources_are_inside_security_gate(self):
        self.assertTrue(security_source_gate._authored("outlook/app.py"))
        self.assertTrue(security_source_gate._authored("outlook/static/js/perspectives.js"))


if __name__ == "__main__":
    unittest.main()
