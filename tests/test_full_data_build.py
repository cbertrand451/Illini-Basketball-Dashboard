"""Exercise whole-build isolation, recovery, and retention of downloaded stats."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

from scrapers import build_transaction as transaction
from scrapers import full_data_build as full
from scrapers import player_bio_scraper as bio


class FullBuildSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / 'data'
        self.processed = self.data / 'processed'
        self.images = self.data / 'images'
        (self.processed / 'players').mkdir(parents=True)
        (self.processed / 'player_stats').mkdir()
        self.images.mkdir()
        self.player = 'Ty Rodgers'
        self.info = ['https://fightingillini.com/sports/mens-basketball/roster/ty-rodgers/1', ['2025-26'], 'Ty_Rodgers.json']
        (self.processed / 'player_list.json').write_text(json.dumps({self.player: self.info}))
        (self.processed / 'players' / 'Ty_Rodgers.json').write_text(json.dumps({
            'name': self.player, 'url': self.info[0], 'seasons': ['2025-26'],
            'header': {'Full Name': self.player, 'Height': '6-6', 'Image URL': 'old-photo'},
            'action photos': [{'url': 'old-action'}],
        }))
        pd.DataFrame([
            {'Season': '2024-25', 'Team': 'Illinois', 'Total Points': 100, 'Overall Wins': 20},
            {'Season': '2025-26', 'Team': 'Illinois', 'Total Points': 200, 'Overall Wins': 10},
        ]).to_csv(self.processed / 'season_stats.csv', index=False)
        pd.DataFrame([{'Player': self.player, 'PTS': 100, 'AST': 30},
                      {'Player': 'Historical teammate', 'PTS': 25, 'AST': 10}]).to_csv(
            self.processed / 'player_stats' / '2025-26.csv', index=False)
        (self.images / 'action_photos.json').write_text('["old-action"]')
        self.before = self.snapshot()

    def snapshot(self):
        return {path.relative_to(self.data): path.read_bytes()
                for root in (self.processed, self.images) for path in root.rglob('*')
                if path.is_file()}

    def fake_index(self, output_path, **kwargs):
        # Mutate the staged index so a later failure proves it was not published.
        players = {self.player: [self.info[0], ['2024-25', '2025-26'], self.info[2]]}
        Path(output_path).write_text(json.dumps(players))
        return players

    def fake_history(self, output_dir, **kwargs):
        path = Path(output_dir) / 'Titles.csv'
        path.parent.mkdir(exist_ok=True)
        path.write_text('Year\n2026\n')
        return {'Titles': str(path)}

    def sources(self, stack, late_failure=False):
        stack.enter_context(patch.object(full, 'DATA_DIR', str(self.processed)))
        stack.enter_context(patch.object(full, 'build_player_index', side_effect=self.fake_index))
        calls = [(pd.DataFrame({'raw': [1]}), pd.DataFrame({'raw': [1]}), (10, 1, 2, 1))]
        calls.append(requests.Timeout('last download failed') if late_failure else calls[0])
        stack.enter_context(patch.object(full, 'scrape_season_stats_w_players', side_effect=calls))
        wide = pd.DataFrame([{'Season': '2025-26', 'Team': 'Illinois', 'Total Points': 300}]).set_index('Team')
        stack.enter_context(patch.object(full, 'create_team_stats_df', return_value=wide))
        stack.enter_context(patch.object(full, 'fix_df', return_value=pd.DataFrame([{'Player': self.player, 'PTS': 120}])))
        stack.enter_context(patch.object(full, 'update_mbb_history_csv_files', side_effect=self.fake_history))
        stack.enter_context(patch.object(bio, 'player_scrape_header_info', return_value=(
            {'Full Name': self.player, 'Weight': '210'}, [{'url': 'new-action'}])))

    def test_late_network_failure_leaves_every_live_output_unchanged(self):
        with ExitStack() as stack:
            self.sources(stack, late_failure=True)
            with self.assertRaisesRegex(requests.Timeout, 'last download failed'):
                full.build_all(start_year=2025, end_year=2026, do_geocode=False)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.data / '.full-data-build.lock').exists())
        self.assertFalse(list(self.data.glob('.full-build-*')))
        self.assertFalse((self.data / '.build-backups').exists())

    def test_invalid_final_profile_cannot_be_published(self):
        def empty_profile(*args, **kwargs):
            (Path(kwargs['output_dir']) / 'Ty_Rodgers.json').write_text('{"header":{}}')
            return []
        with ExitStack() as stack:
            self.sources(stack)
            stack.enter_context(patch.object(full, 'build_player_metadata_files', side_effect=empty_profile))
            with self.assertRaisesRegex(ValueError, 'empty profile'):
                full.build_all(start_year=2025, end_year=2026, do_geocode=False)
        self.assertEqual(self.snapshot(), self.before)

    def test_success_preserves_old_stats_and_creates_complete_snapshot(self):
        with ExitStack() as stack:
            self.sources(stack)
            result = full.build_all(start_year=2025, end_year=2026, do_geocode=False)
        backup = Path(result['backup_path'])
        backed_up = {p.relative_to(backup): p.read_bytes() for p in backup.rglob('*') if p.is_file()}
        self.assertEqual(backed_up, self.before)
        season = pd.read_csv(self.processed / 'season_stats.csv').set_index('Season')
        self.assertEqual(season.loc['2024-25', 'Total Points'], 100)
        self.assertEqual(season.loc['2025-26', 'Total Points'], 300)
        self.assertEqual(season.loc['2025-26', 'Overall Wins'], 10)
        stats = pd.read_csv(self.processed / 'player_stats' / '2025-26.csv').set_index('Player')
        self.assertEqual(stats.loc[self.player, 'PTS'], 120)
        self.assertEqual(stats.loc[self.player, 'AST'], 30)
        self.assertEqual(stats.loc['Historical teammate', 'PTS'], 25)
        self.assertEqual(json.loads((self.images / 'action_photos.json').read_text()), ['new-action', 'old-action'])
        profile = json.loads((self.processed / 'players' / 'Ty_Rodgers.json').read_text())
        self.assertEqual(profile['header']['Image URL'], 'old-photo')
        self.assertEqual(profile['header']['Weight'], '210')
        self.assertEqual(profile['seasons'], ['2024-25', '2025-26'])

    def test_publish_failure_rolls_back_prior_replacements(self):
        original = transaction._replace_file
        count = 0
        def fail_second(source, destination):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('simulated disk failure')
            original(source, destination)
        with ExitStack() as stack:
            self.sources(stack)
            stack.enter_context(patch.object(transaction, '_replace_file', side_effect=fail_second))
            with self.assertRaisesRegex(OSError, 'simulated disk failure'):
                full.build_all(start_year=2025, end_year=2026, do_geocode=False)
        self.assertGreater(count, 2)  # Rollback actually ran.
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(len(list((self.data / '.build-backups').iterdir())), 1)

    def test_concurrent_local_changes_are_not_overwritten(self):
        path = self.processed / 'player_list.json'
        with self.assertRaisesRegex(RuntimeError, 'changed while the build'):
            with transaction.staged_build(self.processed) as workspace:
                path.write_text('{"user-edited":true}')
                (workspace.processed / 'player_list.json').write_text('{}')
        self.assertEqual(path.read_text(), '{"user-edited":true}')

    def test_interrupt_after_file_replacement_restores_original(self):
        original = transaction._replace_file
        count = 0
        def interrupt_after_first(source, destination):
            nonlocal count
            count += 1
            original(source, destination)
            if count == 1:
                raise KeyboardInterrupt()
        with ExitStack() as stack:
            self.sources(stack)
            stack.enter_context(patch.object(transaction, '_replace_file', side_effect=interrupt_after_first))
            with self.assertRaises(KeyboardInterrupt):
                full.build_all(start_year=2025, end_year=2026, do_geocode=False)
        self.assertEqual(self.snapshot(), self.before)

    def test_blank_statistic_cells_keep_saved_values(self):
        previous = pd.DataFrame([{'Player': self.player, 'PTS': 100, 'AST': 30}])
        fresh = pd.DataFrame([{'Player': self.player, 'PTS': ' ', 'AST': 0}])
        merged = full._merge_stats(previous, fresh, ['Player'])
        self.assertEqual(merged.iloc[0]['PTS'], 100)
        self.assertEqual(merged.iloc[0]['AST'], 0)

    def test_two_full_builds_cannot_run_together(self):
        with transaction.staged_build(self.processed):
            with self.assertRaisesRegex(RuntimeError, 'Another full build'):
                with transaction.staged_build(self.processed):
                    self.fail('Concurrent build was allowed')
        self.assertFalse((self.data / '.full-data-build.lock').exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_empty_stats_do_not_replace_saved_csv(self):
        path = self.processed / 'season_stats.csv'
        with patch.object(full, 'scrape_season_stats_w_players', return_value=(pd.DataFrame(), pd.DataFrame(), (None, None))):
            with self.assertRaisesRegex(ValueError, 'No season statistics'):
                full.update_season_stats_csv(str(path), 2025, 2026)
            with self.assertRaisesRegex(ValueError, 'No player statistics'):
                full.build_player_stats_files(str(self.processed / 'player_stats'), 2025, 2026)
        self.assertEqual(self.snapshot(), self.before)

    def test_http_errors_are_not_treated_as_successful_empty_downloads(self):
        reply = Mock()
        reply.raise_for_status.side_effect = requests.HTTPError('503')
        with patch.object(full.requests, 'get', return_value=reply):
            with self.assertRaises(requests.HTTPError):
                full.scrape_season_stats_w_players('2025-26')
            with self.assertRaises(requests.HTTPError):
                full.update_mbb_history_csv_files(str(self.processed / 'history'))

    def test_truncated_history_table_cannot_replace_saved_history(self):
        directory = self.processed / 'mbb_history_csv'
        directory.mkdir()
        path = directory / 'Titles.csv'
        path.write_text('Year\n2024\n2025\n')
        before = path.read_bytes()
        reply = Mock(text='<table class="release"><tr><th>Titles</th></tr>'
                          '<tr><td>Year</td></tr><tr><td>2026</td></tr></table>')
        with patch.object(full.requests, 'get', return_value=reply):
            with self.assertRaisesRegex(ValueError, 'lost rows or columns'):
                full.update_mbb_history_csv_files(str(directory))
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
