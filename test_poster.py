import unittest
from datetime import datetime, date
from zoneinfo import ZoneInfo
from telegram_poster import (
    is_eligible_football_match,
    format_match_card,
    build_combined_post,
    chunk_post_message,
    format_local_time,
    MYT_TZ
)

class TestTelegramPoster(unittest.TestCase):

    def test_top_7_european_leagues_allowed(self):
        # England
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Arsenal vs Chelsea", "competition": "Premier League"})
        self.assertTrue(ok)
        self.assertEqual(comp, "PREMIER LEAGUE")

        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Leeds vs Sunderland", "competition": "EFL Championship"})
        self.assertTrue(ok)
        self.assertEqual(comp, "EFL CHAMPIONSHIP")

        # Spain
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Real Madrid vs Barcelona", "competition": "La Liga EA Sports"})
        self.assertTrue(ok)
        self.assertEqual(comp, "LA LIGA")

        # Italy
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Monza vs Cagliari", "id": "monza-vs-cagliari-serie-a-1792427400"})
        self.assertTrue(ok)
        self.assertEqual(comp, "SERIE A")

        # Germany
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Bayern Munich vs Borussia Dortmund", "competition": "Bundesliga"})
        self.assertTrue(ok)
        self.assertEqual(comp, "BUNDESLIGA")

        # France
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "PSG vs Marseille", "competition": "Ligue 1"})
        self.assertTrue(ok)
        self.assertEqual(comp, "LIGUE 1")

        # Portugal
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Benfica vs Porto", "competition": "Primeira Liga"})
        self.assertTrue(ok)
        self.assertEqual(comp, "PRIMEIRA LIGA")

        # Netherlands
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Ajax vs Feyenoord", "competition": "Eredivisie"})
        self.assertTrue(ok)
        self.assertEqual(comp, "EREDIVISIE")

    def test_approved_cups_allowed(self):
        # FA Cup
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Manchester City vs Newcastle", "competition": "The Emirates FA Cup"})
        self.assertTrue(ok)
        self.assertEqual(comp, "FA CUP")

        # Copa del Rey
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Athletic Bilbao vs Barcelona", "competition": "Copa del Rey"})
        self.assertTrue(ok)
        self.assertEqual(comp, "COPA DEL REY")

    def test_uefa_club_competitions_allowed(self):
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Real Madrid vs Bayern Munich", "competition": "UEFA Champions League"})
        self.assertTrue(ok)
        self.assertEqual(comp, "UEFA CHAMPIONS LEAGUE")

        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Roma vs Athletic Bilbao", "competition": "UEFA Europa League"})
        self.assertTrue(ok)
        self.assertEqual(comp, "UEFA EUROPA LEAGUE")

        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Chelsea vs Gent", "competition": "UEFA Conference League"})
        self.assertTrue(ok)
        self.assertEqual(comp, "UEFA CONFERENCE LEAGUE")

    def test_senior_international_tournaments_allowed(self):
        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Brazil vs Argentina", "competition": "FIFA World Cup Qualifiers"})
        self.assertTrue(ok)
        self.assertEqual(comp, "FIFA WORLD CUP")

        comp, ok = is_eligible_football_match({"sport": "football", "eventName": "Spain vs France", "competition": "UEFA Nations League"})
        self.assertTrue(ok)
        self.assertEqual(comp, "UEFA NATIONS LEAGUE")

    def test_exclusions_rejected(self):
        # Non-football sports
        _, ok = is_eligible_football_match({"sport": "cricket", "eventName": "India vs Pakistan", "competition": "ICC World Cup"})
        self.assertFalse(ok)

        # Unapproved domestic cups (Carabao Cup, Coppa Italia, DFB-Pokal)
        _, ok = is_eligible_football_match({"sport": "football", "eventName": "Chelsea vs Wolves", "competition": "Carabao Cup"})
        self.assertFalse(ok)

        _, ok = is_eligible_football_match({"sport": "football", "eventName": "Juventus vs Milan", "competition": "Coppa Italia"})
        self.assertFalse(ok)

        # Leagues outside the top 7
        _, ok = is_eligible_football_match({"sport": "football", "eventName": "Degerfors vs Kalmar", "id": "ppv-degerfors-if-vs-kalmar-ff"})
        self.assertFalse(ok)

        _, ok = is_eligible_football_match({"sport": "football", "eventName": "Monterrey vs Pachuca", "competition": "Liga MX"})
        self.assertFalse(ok)

        # Friendlies
        _, ok = is_eligible_football_match({"sport": "football", "eventName": "Liverpool vs AC Milan", "competition": "Club Friendly"})
        self.assertFalse(ok)

        # Youth / Reserves
        _, ok = is_eligible_football_match({"sport": "football", "eventName": "Arsenal U21 vs Chelsea U21", "competition": "Premier League 2"})
        self.assertFalse(ok)

    def test_timezone_formatting_and_rollover(self):
        base_date = date(2026, 10, 19) # Monday

        # Match 1: 22:00 MYT Monday (14:00 UTC)
        # 14:00 UTC -> MYT 22:00 (same day), New York 10:00 (same day EDT UTC-4)
        dt1 = datetime(2026, 10, 19, 14, 0, tzinfo=ZoneInfo("UTC"))
        match1 = {
            "eventName": "Arsenal vs Chelsea",
            "_kickoff_dt": dt1,
            "slug": "test-match-1"
        }
        card1 = format_match_card(match1, is_live=False, base_date=base_date, is_html=True)
        self.assertIn("<b>Arsenal vs Chelsea</b> · <code>22:00 MYT</code>", card1)
        self.assertIn("<code>DHA 20:00 · DEL 19:30 · WDC 10:00</code>", card1)
        self.assertIn("<code>JKT 21:00 · ABJ 15:00 · SGT 22:00</code>", card1)
        self.assertIn("<a href=\"https://sportzfyplay.com/watch?v=test-match-1\">▶ Watch live in HD</a>", card1)
        # No city flags or fake crests
        self.assertNotIn("⚪", card1)
        self.assertNotIn("🇲🇾", card1)

        # Match 2: 02:00 MYT Tuesday (18:00 UTC Monday)
        # MYT is Tuesday 02:00 -> rollover suffix Tue
        dt2 = datetime(2026, 10, 19, 18, 0, tzinfo=ZoneInfo("UTC"))
        match2 = {
            "eventName": "Real Madrid vs Bayern Munich",
            "_kickoff_dt": dt2,
            "slug": "test-match-2"
        }
        card2 = format_match_card(match2, is_live=False, base_date=base_date, is_html=True)
        self.assertIn("<b>Real Madrid vs Bayern Munich</b> · <code>02:00 MYT Tue</code>", card2)

    def test_combined_post_structure(self):
        base_date = date(2026, 10, 19)
        dt = datetime(2026, 10, 19, 14, 0, tzinfo=ZoneInfo("UTC"))
        match = {
            "eventName": "Arsenal vs Chelsea",
            "_comp": "PREMIER LEAGUE",
            "_kickoff_dt": dt,
            "slug": "test-match"
        }

        # Upcoming only
        post = build_combined_post({"LIVE": [], "UPCOMING": [match]}, base_date, is_html=True)
        self.assertIn("<b>⚽ SPORTZFYPLAY · DAILY FIXTURES</b>", post)
        self.assertIn("<code>MON 19 OCT · MYT</code>", post)
        self.assertIn("<b>PREMIER LEAGUE</b>", post)
        self.assertIn("<code>MYT Malaysia · DHA Dhaka · DEL New Delhi</code>", post)
        self.assertIn("<code>WDC Washington DC · JKT Jakarta · ABJ Abuja · SGT Singapore</code>", post)
        # Ensure rules/separators and verbose lines are absent
        self.assertNotIn("━━━━━━━━━━━━━━━━━━━━", post)
        self.assertNotIn("Published daily at 8:00 PM MYT", post)
        self.assertNotIn("Free Live Sports", post)
        self.assertNotIn("<b>LIVE NOW</b>", post)

        # With live match
        post_live = build_combined_post({"LIVE": [match], "UPCOMING": []}, base_date, is_html=True)
        self.assertIn("<b>LIVE NOW</b>", post_live)

        # Empty schedule
        post_empty = build_combined_post({"LIVE": [], "UPCOMING": []}, base_date, is_html=True)
        self.assertIn("No qualifying fixtures scheduled.", post_empty)

    def test_chunking(self):
        short_msg = "Short message"
        self.assertEqual(len(chunk_post_message(short_msg, max_chars=100)), 1)

        long_msg = "\n".join([f"Line {i} content text" for i in range(100)])
        chunks = chunk_post_message(long_msg, max_chars=200)
        self.assertGreater(len(chunks), 1)
        # All lines preserved
        reconstructed = "\n".join(chunks)
        for i in range(100):
            self.assertIn(f"Line {i} content text", reconstructed)

if __name__ == "__main__":
    unittest.main()
