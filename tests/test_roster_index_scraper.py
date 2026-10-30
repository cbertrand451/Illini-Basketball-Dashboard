"""Roster safety regressions; no live requests or repository data writes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from scrapers import full_data_build as full
from scrapers import roster_index_scraper as roster


def bio(name, identifier=1):
    return f"https://fightingillini.com/sports/mens-basketball/roster/{name}/{identifier}"


def roster_html(table=False):
    links = [f'<a href="{bio(f"player-{i}", i)}">Player {i}</a>' for i in range(5)]
    if table:
        # The advertisement table precedes the actual roster. No tbody required.
        return '<table><tr><td><a href="#">Skip Ad</a></td></tr></table>' + (
            '<table>' + ''.join(f'<tr><td>{link}</td></tr>' for link in links) + '</table>'
        )
    return ''.join(f'<li class="sidearm-roster-player"><div class="sidearm-roster-player-name">{link}</div></li>' for link in links)


def response(html='', status=200):
    result = Mock(status_code=status, text=html)
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


class RosterSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'player_list.json'
        self.original = {'Historical Player': [bio('historical', 100), ['1990-91'], 'Historical_Player.json']}
        self.path.write_text(json.dumps(self.original))
        self.original_bytes = self.path.read_bytes()

    def test_cards_and_ad_before_table(self):
        for table in (True, False):
            with self.subTest(table=table):
                parsed = roster._parse_roster(roster_html(table))
                self.assertEqual(len(parsed), 5)
                self.assertNotIn('Skip Ad', dict(parsed))

    def test_only_player_bio_links_are_accepted(self):
        html = '<table>' + ''.join(f'<tr><td><a href="{href}">{name}</a></td></tr>' for name, href in [
            ('Skip Ad', '#'), ('Roster', '/sports/mens-basketball/roster'),
            ('Wrong sport', '/sports/football/roster/person/1'),
            ('External', 'https://example.com/sports/mens-basketball/roster/person/1'),
            ('Skip Ad', bio('skip-ad')), ('', bio('empty')),
            ('Doe, John', '/sports/mens-basketball/roster/john-doe/123'),
        ]) + '</table>'
        self.assertEqual(roster._parse_roster(html), [('John Doe', bio('john-doe', 123))])

    @patch.object(roster.requests, 'get')
    def test_ad_page_aborts_full_build_before_later_steps(self, get):
        get.return_value = response('<table><tr><td><a href="#">Skip Ad</a></td></tr></table>')
        with patch.object(full, 'DATA_DIR', self.temp.name), patch.object(full, 'update_season_stats_csv') as stats:
            with self.assertRaisesRegex(ValueError, 'valid player bio links'):
                full.build_all(start_year=2025, end_year=2026, do_geocode=False)
            stats.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs['timeout'], 30)

    @patch.object(roster.requests, 'get')
    def test_partial_historical_roster_cannot_overwrite_index(self, get):
        get.side_effect = [response(roster_html()), response('<html>No roster</html>')]
        with self.assertRaises(ValueError):
            roster.build_player_index(str(self.path), 2025, 2026)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        self.assertFalse(Path(str(self.path) + '.bak').exists())

    @patch.object(roster.requests, 'get')
    def test_success_merges_history_and_preserves_seasons_and_backup(self, get):
        get.return_value = response(roster_html())
        players = roster.build_player_index(str(self.path), 2025, 2026)
        self.assertEqual(players['Historical Player'], self.original['Historical Player'])
        self.assertEqual(players['Player 0'][1], ['2025-26'])
        self.assertEqual(len(players), 6)
        self.assertEqual(Path(str(self.path) + '.bak').read_bytes(), self.original_bytes)
        roster.build_player_index(str(self.path), 2025, 2026)
        again = json.loads(self.path.read_text())
        self.assertEqual(players, again)
        self.assertEqual(full.build_player_index, roster.build_player_index)

    @patch.object(roster.requests, 'get')
    def test_missing_historical_page_retains_cached_players(self, get):
        get.side_effect = [response(roster_html()), response(status=404)]
        players = roster.build_player_index(str(self.path), 1990, 1991)
        self.assertEqual(players['Historical Player'], self.original['Historical Player'])

    @patch.object(roster.requests, 'get')
    def test_http_failure_preserves_original(self, get):
        get.side_effect = [response(roster_html()), response(status=503)]
        with self.assertRaises(requests.HTTPError):
            roster.build_player_index(str(self.path), 2025, 2026)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    @patch.object(roster.requests, 'get')
    def test_direct_current_roster_scrape_preserves_history(self, get):
        get.return_value = response(roster_html())
        players = roster.scrape_rosters(str(self.path))
        self.assertEqual(players['Historical Player'], self.original['Historical Player'])

    @patch.object(roster.requests, 'get')
    def test_invalid_cache_is_not_silently_replaced(self, get):
        self.path.write_text(json.dumps({'Skip Ad': ['#', [], 'Skip_Ad.json']}))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Restore the last valid index'):
            roster.build_player_index(str(self.path), 2025, 2026)
        get.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_incomplete_write_is_rejected(self):
        with self.assertRaises(ValueError):
            roster._write_player_index(str(self.path), {'Other': [bio('other'), []]})
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    @patch.object(roster.os, 'replace', side_effect=OSError('simulated write failure'))
    def test_failed_replacement_keeps_original(self, replace):
        with self.assertRaises(OSError):
            roster._write_player_index(str(self.path), self.original)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ['player_list.json', 'player_list.json.bak'])


if __name__ == '__main__':
    unittest.main()
