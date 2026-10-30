"""Protect cached profile data against failed or partial source downloads."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from scrapers import full_data_build as full
from scrapers import player_bio_scraper as bio


PROFILE_HTML = '''<span class="sidearm-roster-player-first-name">Ty</span>
<span class="sidearm-roster-player-last-name">Rodgers</span>
<div class="sidearm-roster-player-image"><img src="https://example.com/ty.jpg"></div>
<div class="sidearm-roster-player-fields"><ul><li>
<span class="sidearm-roster-player-field-label">Hometown</span><span>Saginaw, Mich.</span>
</li></ul></div>'''


class PlayerBioSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'data' / 'processed' / 'players'
        self.output.mkdir(parents=True)
        self.index = self.output.parent / 'player_list.json'
        self.index.write_text(json.dumps({'Ty Rodgers': ['https://fightingillini.com/sports/mens-basketball/roster/ty-rodgers/15206', ['2025-26'], 'Ty_Rodgers.json']}))
        self.profile = self.output / 'Ty_Rodgers.json'
        self.previous = {
            'name': 'Ty Rodgers', 'url': 'cached-url', 'seasons': ['2024-25'],
            'header': {'Full Name': 'Ty Rodgers', 'Hometown': 'Saginaw, Mich.', 'Height': '6-6', 'Image URL': 'old-photo'},
            'action photos': [{'url': 'old-action', 'credit': 'Old credit'}],
            'geocode': {'hometown': 'Saginaw, Mich.', 'lat': 43.42, 'lon': -83.94, 'is_illinois': False},
        }
        self.profile.write_text(json.dumps(self.previous))
        self.photos = self.output.parent.parent / 'images' / 'action_photos.json'
        self.photos.parent.mkdir()
        self.photos.write_text(json.dumps(['historical-action', 'old-action']))
        self.before = {p: p.read_bytes() for p in (self.profile, self.photos)}

    def build(self):
        return full.build_player_metadata_files(
            str(self.index), str(self.output), do_geocode=False,
            images_dir=str(self.photos.parent),
        )

    def assert_unchanged(self):
        for path, contents in self.before.items():
            self.assertEqual(path.read_bytes(), contents)

    @patch.object(bio.requests, 'get')
    def test_http_error_does_not_erase_profile_or_gallery(self, get):
        get.return_value.raise_for_status.side_effect = requests.HTTPError('403 Forbidden')
        with self.assertRaisesRegex(ValueError, 'Ty Rodgers.*403 Forbidden'):
            self.build()
        self.assert_unchanged()
        self.assertEqual(get.call_args.kwargs['timeout'], 30)

    @patch.object(bio.requests, 'get')
    def test_ad_page_is_not_a_successful_profile(self, get):
        get.return_value.text = '<html><a href="#">Skip Ad</a></html>'
        with self.assertRaisesRegex(ValueError, 'No recognizable player profile'):
            self.build()
        self.assert_unchanged()

    @patch.object(bio.requests, 'get')
    def test_network_error_is_visible_and_preserves_data(self, get):
        get.side_effect = requests.Timeout('timed out')
        with self.assertRaisesRegex(ValueError, 'timed out'):
            self.build()
        self.assert_unchanged()

    @patch.object(bio.requests, 'get')
    def test_legacy_html_is_parsed_and_missing_fields_are_retained(self, get):
        get.return_value.text = PROFILE_HTML
        paths = self.build()
        data = json.loads(self.profile.read_text())
        self.assertEqual(paths, [str(self.profile)])
        self.assertEqual(data['header']['Image URL'], 'https://example.com/ty.jpg')
        self.assertEqual(data['header']['Height'], '6-6')
        self.assertEqual(data['geocode'], self.previous['geocode'])
        self.assertEqual(data['action photos'], self.previous['action photos'])
        self.assertEqual(data['seasons'], ['2025-26'])
        self.assertEqual(json.loads(self.photos.read_text()), ['historical-action', 'old-action'])
        self.assertEqual(Path(str(self.profile) + '.bak').read_bytes(), self.before[self.profile])
        self.build()
        self.assertEqual(data, json.loads(self.profile.read_text()))

    @patch.object(bio, 'player_scrape_header_info')
    def test_failure_later_in_batch_leaves_earlier_profile_untouched(self, scrape):
        players = json.loads(self.index.read_text())
        players['Other'] = ['other-url', [], 'Other.json']
        self.index.write_text(json.dumps(players))
        scrape.side_effect = [({'Full Name': 'Ty Rodgers', 'Height': '6-7'}, []), ValueError('changed layout')]
        with self.assertRaisesRegex(ValueError, 'changed layout'):
            self.build()
        self.assert_unchanged()
        self.assertFalse((self.output / 'Other.json').exists())
        self.assertFalse(Path(str(self.profile) + '.bak').exists())

    @patch.object(bio, 'player_scrape_header_info')
    def test_empty_result_cannot_be_written(self, scrape):
        scrape.return_value = ({}, [])
        with self.assertRaisesRegex(ValueError, 'Empty profile'):
            self.build()
        self.assert_unchanged()

    @patch.object(bio, 'player_scrape_header_info')
    def test_partial_header_keeps_photo_and_gallery_adds_new_urls(self, scrape):
        scrape.return_value = ({'Full Name': 'Ty Rodgers', 'Image URL': ''}, [{'url': 'new-action'}])
        self.build()
        data = json.loads(self.profile.read_text())
        self.assertEqual(data['header']['Image URL'], 'old-photo')
        self.assertEqual({p['url'] for p in data['action photos']}, {'old-action', 'new-action'})
        self.assertEqual(set(json.loads(self.photos.read_text())), {'historical-action', 'old-action', 'new-action'})

    @patch.object(bio.requests, 'get')
    def test_both_build_commands_share_protected_implementation(self, get):
        self.assertIs(full.build_player_metadata_files, bio.build_player_bio_files)
        self.assertIs(full.player_scrape_header_info, bio.player_scrape_header_info)
        self.index.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'empty/invalid'):
            self.build()
        get.assert_not_called()
        self.assert_unchanged()


if __name__ == '__main__':
    unittest.main()
