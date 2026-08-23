import unittest
from unittest import mock

import vlr


def listing_match(
    match_id: str,
    slug: str,
    event: str,
    status: str = "Upcoming",
    score_one: str = "-",
    score_two: str = "-",
) -> str:
    return f"""
    <a href="/{match_id}/{slug}" class="wf-module-item match-item">
      <div class="match-item-time">4:00 PM</div>
      <div class="match-item-vs">
        <div class="match-item-vs-team">
          <div class="match-item-vs-team-name"><div class="text-of">Alpha</div></div>
          <div class="match-item-vs-team-score">{score_one}</div>
        </div>
        <div class="match-item-vs-team">
          <div class="match-item-vs-team-name"><div class="text-of">Bravo</div></div>
          <div class="match-item-vs-team-score">{score_two}</div>
        </div>
      </div>
      <div class="match-item-eta">
        <div class="ml-status">{status}</div><div class="ml-eta">1h 20m</div>
      </div>
      <div class="match-item-event text-of">
        <div class="match-item-event-series text-of">Playoffs - Upper Final</div>
        {event}
      </div>
    </a>
    """


def live_detail(score_one: int = 9, score_two: int = 0) -> str:
    rounds = []
    for number in range(1, score_one + score_two + 1):
        rounds.append(f"""
        <div class="vlr-rounds-row-col">
          <div class="rnd-num">{number}</div>
          <div class="rnd-sq mod-win mod-t"></div><div class="rnd-sq"></div>
        </div>
        """)
    return f"""
    <div class="vm-stats-gamesnav-item mod-live" data-game-id="42">Ascent</div>
    <div class="vm-stats-game" data-game-id="42">
      <div class="vm-stats-game-header">
        <div class="team">
          <div class="score">{score_one}</div><div class="team-name">Alpha</div>
          <span class="mod-t">{score_one}</span><span class="mod-ct">0</span>
        </div>
        <div class="map"><div>Ascent <span class="picked">PICK</span></div></div>
        <div class="team mod-right">
          <div class="team-name">Bravo</div><span class="mod-ct">0</span><span class="mod-t">0</span>
          <div class="score">{score_two}</div>
        </div>
      </div>
      <div class="vlr-rounds-row">{''.join(rounds)}</div>
    </div>
    """


class EventFilterTests(unittest.TestCase):
    def test_allows_top_tier_events(self):
        allowed = [
            "VCT 2026: Americas Stage 2",
            "VCT 2026: EMEA Kickoff",
            "Valorant Masters Toronto 2025",
            "Valorant Champions 2025",
            "Champions Tour 2024: Pacific Stage 1",
            "Valorant Champions Tour 2023: LOCK//IN Sao Paulo",
        ]
        for event in allowed:
            with self.subTest(event=event):
                self.assertTrue(vlr.is_top_tier_vct(event))

    def test_rejects_tier_two_and_other_events(self):
        rejected = [
            "Valorant Challengers 2026: North America",
            "VCT 2026: Pacific Ascension",
            "Game Changers 2026: Brazil",
            "VCL 2026: France",
            "Valorant Champions Tour 2026: OFF//SEASON",
            "Red Bull Home Ground",
            "College VALORANT 2026",
        ]
        for event in rejected:
            with self.subTest(event=event):
                self.assertFalse(vlr.is_top_tier_vct(event))

    def test_path_fallback_still_applies_exclusions(self):
        self.assertTrue(vlr.is_top_tier_vct("", "/123/alpha-vs-bravo-vct-2026-emea-stage-2"))
        self.assertFalse(
            vlr.is_top_tier_vct("VCT 2026: EMEA Ascension", "/123/vct-2026-emea-ascension")
        )


class ParsingTests(unittest.TestCase):
    def test_parses_schedule_fields_and_series_scores(self):
        html = """
        <div class="wf-label mod-large">Sun, August 23, 2026 <span>Today</span></div>
        """ + listing_match(
            "100", "alpha-vs-bravo-vct-2026-americas-stage-2", "VCT 2026: Americas Stage 2",
            status="LIVE", score_one="0", score_two="1",
        )
        matches = vlr.parse_matches(html)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["date"], "Sun, August 23, 2026")
        self.assertEqual(matches[0]["status"], "live")
        self.assertEqual(matches[0]["teams"][0]["name"], "Alpha")
        self.assertEqual(matches[0]["teams"][1]["seriesScore"], 1)

    def test_parses_live_map_score_and_attacking_team(self):
        detail = vlr.parse_detail(live_detail())
        self.assertEqual(detail["map"], "Ascent")
        self.assertEqual(detail["round"], 10)
        self.assertEqual(detail["teams"][0]["mapScore"], 9)
        self.assertEqual(detail["attackingTeam"], 0)

    def test_infers_attacking_side_across_halftime_and_overtime(self):
        initial = ["t", "ct"]
        self.assertEqual(vlr.infer_attacking_team([6, 5], initial, []), 0)
        self.assertEqual(vlr.infer_attacking_team([7, 5], initial, []), 1)
        self.assertEqual(vlr.infer_attacking_team([12, 12], initial, []), 0)
        rounds = [{"number": 25, "sides": ["t", "ct"]}]
        self.assertEqual(vlr.infer_attacking_team([13, 12], initial, rounds), 1)

    def test_snapshot_filters_and_enriches_all_live_vct_matches(self):
        schedule = '<div class="wf-label mod-large">Today</div>'
        schedule += listing_match(
            "100", "alpha-vs-bravo-vct-2026-americas-stage-2", "VCT 2026: Americas Stage 2",
            status="LIVE", score_one="0", score_two="1",
        )
        schedule += listing_match(
            "101", "alpha-vs-bravo-vct-2026-emea-stage-2", "VCT 2026: EMEA Stage 2",
            status="LIVE", score_one="1", score_two="0",
        )
        schedule += listing_match(
            "102", "alpha-vs-bravo-game-changers-2026", "Game Changers 2026: EMEA",
        )
        schedule += listing_match(
            "103", "alpha-vs-bravo-vct-2026-pacific-stage-2", "VCT 2026: Pacific Stage 2",
        )

        def fetcher(url):
            if url == vlr.MATCHES_URL:
                return schedule
            return live_detail()

        snapshot = vlr.build_snapshot(fetcher)
        self.assertEqual(len(snapshot["live"]), 2)
        self.assertEqual(len(snapshot["upcoming"]), 1)
        self.assertEqual(snapshot["live"][0]["teams"][1]["seriesScore"], 1)
        self.assertEqual(snapshot["live"][0]["teams"][0]["mapScore"], 9)


class FetchLimitTests(unittest.TestCase):
    class FakeHeaders:
        def get_content_charset(self):
            return "utf-8"

    class FakeResponse:
        def __init__(self, payload: bytes):
            self.payload = payload
            self.status = 200
            self.headers = FetchLimitTests.FakeHeaders()

        def read(self, size=-1):
            return self.payload[:size] if size >= 0 else self.payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_reads_at_most_one_byte_past_ceiling(self):
        payload = b"<html>fine</html>"
        response = self.FakeResponse(payload)
        response.read = mock.Mock(
            side_effect=lambda size=-1: payload[:size] if size >= 0 else payload
        )
        with mock.patch.object(vlr, "urlopen", return_value=response):
            self.assertEqual(vlr.fetch_html("https://www.vlr.gg/matches/"), "<html>fine</html>")
            response.read.assert_called_once_with(vlr.MAX_HTML_BYTES + 1)

    def test_rejects_oversized_response_before_parsing(self):
        oversized = b"x" * (vlr.MAX_HTML_BYTES + 5)
        with mock.patch.object(vlr, "urlopen", return_value=self.FakeResponse(oversized)):
            with self.assertRaises(RuntimeError):
                vlr.fetch_html("https://www.vlr.gg/matches/")


class BoundingTests(unittest.TestCase):
    def test_bounded_match_clamps_fields_and_drops_foreign_urls(self):
        bounded = vlr.bounded_match({
            "id": "9" * 64,
            "url": "https://evil.example/123/steal",
            "event": "E" * 500,
            "series": "S" * 500,
            "date": "D" * 500,
            "time": "T" * 500,
            "eta": "H" * 500,
            "status": "live",
            "teams": [
                {"name": "N" * 500, "seriesScore": 2, "mapScore": True},
                {"name": "Ok", "seriesScore": None, "mapScore": 7},
                {"name": "Dropped", "seriesScore": 0},
            ],
            "map": "M" * 500,
            "attackingTeam": 7,
            "round": "13",
            "gameId": "G" * 500,
        })
        self.assertEqual(len(bounded["id"]), vlr.MAX_SHORT_TEXT_CHARS)
        self.assertEqual(bounded["url"], "")
        for field in ("event", "series", "date", "time"):
            self.assertEqual(len(bounded[field]), vlr.MAX_TEXT_CHARS)
        self.assertEqual(len(bounded["eta"]), vlr.MAX_SHORT_TEXT_CHARS)
        self.assertEqual(len(bounded["teams"]), 2)
        self.assertEqual(len(bounded["teams"][0]["name"]), vlr.MAX_TEXT_CHARS)
        self.assertIsNone(bounded["teams"][0]["mapScore"])
        self.assertIsNone(bounded["attackingTeam"])
        self.assertIsNone(bounded["round"])
        self.assertEqual(len(bounded["gameId"]), vlr.MAX_SHORT_TEXT_CHARS)

    def test_bounded_match_keeps_valid_vlr_url(self):
        url = "https://www.vlr.gg/12345/alpha-vs-bravo"
        self.assertEqual(vlr.bounded_match({"url": url})["url"], url)

    def test_snapshot_bounds_items_and_field_lengths(self):
        schedule = '<div class="wf-label mod-large">Today</div>'
        for index in range(12):
            schedule += listing_match(
                str(index), f"alpha-vs-bravo-vct-2026-americas-stage-{index}",
                "VCT 2026: Americas Stage " + "X" * 400,
            )

        def fetcher(url):
            return schedule

        snapshot = vlr.build_snapshot(fetcher)
        self.assertEqual(len(snapshot["upcoming"]), vlr.MAX_UPCOMING)
        for match in snapshot["upcoming"]:
            self.assertLessEqual(len(match["event"]), vlr.MAX_TEXT_CHARS)

    def test_snapshot_bounds_warning_text(self):
        schedule = '<div class="wf-label mod-large">Today</div>'
        schedule += listing_match(
            "100", "alpha-vs-bravo-vct-2026-americas-stage-2", "VCT 2026: Americas Stage 2",
            status="LIVE", score_one="0", score_two="1",
        )

        def fetcher(url):
            if url == vlr.MATCHES_URL:
                return schedule
            raise ValueError("F" * 1000)

        snapshot = vlr.build_snapshot(fetcher)
        self.assertEqual(len(snapshot["warning"]), vlr.MAX_WARNING_CHARS)


    def test_snapshot_warning_empty_when_all_details_succeed(self):
        schedule = '<div class="wf-label mod-large">Today</div>'
        schedule += listing_match(
            "100", "alpha-vs-bravo-vct-2026-americas-stage-2", "VCT 2026: Americas Stage 2",
            status="LIVE", score_one="0", score_two="1",
        )

        def fetcher(url):
            if url == vlr.MATCHES_URL:
                return schedule
            return live_detail()

        snapshot = vlr.build_snapshot(fetcher)
        self.assertEqual(len(snapshot["live"]), 1)
        self.assertEqual(snapshot["warning"], "")


if __name__ == "__main__":
    unittest.main()
