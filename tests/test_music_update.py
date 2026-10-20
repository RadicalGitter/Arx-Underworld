import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import amb
import music_update
import router_update
import score


class MusicUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root/'game'
        self.mapping = self.root/'mapping.csv'
        with self.mapping.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['enabled', 'ambiance', 'track', 'gain', 'role'])
            writer.writeheader()
            for cue in ('ambient_bunker', 'ambient_other'):
                writer.writerow(dict(enabled='1', ambiance=cue, track='uw1_10', gain='.9', role='exploration'))
        self.sample = 'sfx/uwscore/uw1_10_12345678.wav'
        sample = score.encode_wav(22050, b'\0\0'*2205)
        self.before = amb.Ambiance(0x01000003, [
            amb.music_track(0x01000003, 'sfx/uwscore/uw2_13_12345678.wav', .9),
            amb.music_track(0x01000003, 'sfx/drips.wav', .4)]).encode()
        self.paths = ['sfx/ambiance/ambient_uwscore_m001.amb', 'sfx/ambiance/ambient_uwscore_m002.amb']
        entries = []
        for path, data in [(self.sample, sample)] + [(p, self.before) for p in self.paths]:
            score.atomic(self.game/path, data)
            original = b'original owner ambience' if path.endswith('.amb') else None
            if original:
                score.atomic(self.game/'.uwscore-state/backups'/path, original)
            entries.append(dict(path=path, installed=score.sha(data), original=score.sha(original) if original else None))
        score.save_json(score.state_path(self.game), dict(status='installed', entries=entries))
        self.stage = self.root/'stage'
        music_update.prepare(self.game, 'uw2_13', 'uw1_10', self.stage, self.mapping)

    def test_all_references_preserve_scheduling_environment_and_uninstall(self):
        unrelated = self.game/'player.asl'
        unrelated.write_bytes(b'owner script')
        with patch.object(router_update, 'require_closed'):
            self.assertEqual(music_update.apply(self.game, self.stage), 'applied')
            self.assertEqual(music_update.apply(self.game, self.stage), 'already applied')
        before = amb.parse(self.before)
        state = json.loads(score.state_path(self.game).read_text())
        for path in self.paths:
            after = amb.parse((self.game/path).read_bytes())
            self.assertEqual(after.tracks[0].path, self.sample)
            self.assertEqual(after.tracks[0].tail, before.tracks[0].tail)
            self.assertEqual(after.tracks[1].encode(), before.tracks[1].encode())
            self.assertEqual(next(e['installed'] for e in state['entries'] if e['path']==path), score.sha((self.game/path).read_bytes()))
        self.assertEqual(unrelated.read_bytes(), b'owner script')
        score.uninstall(self.game)
        for path in self.paths:
            self.assertEqual((self.game/path).read_bytes(), b'original owner ambience')

    def test_owner_edits_and_changed_replacement_are_rejected_before_any_write(self):
        for path in (self.paths[1], self.sample):
            dest = self.game/path
            original = dest.read_bytes()
            dest.write_bytes(b'owner edit')
            with patch.object(router_update, 'require_closed'), self.assertRaises(ValueError):
                music_update.apply(self.game, self.stage)
            self.assertEqual((self.game/self.paths[0]).read_bytes(), self.before)
            dest.write_bytes(original)

    def test_running_game_guard_prevents_writes(self):
        with patch.object(router_update, 'require_closed', side_effect=ValueError('running')), self.assertRaises(ValueError):
            music_update.apply(self.game, self.stage)
        self.assertEqual((self.game/self.paths[0]).read_bytes(), self.before)

    def test_interrupted_multi_cue_update_can_resume(self):
        real_atomic = score.atomic
        def interrupt(path, data):
            real_atomic(path, data)
            if path == self.game/self.paths[0]:
                raise OSError('interrupted after first cue')
        with patch.object(router_update, 'require_closed'), patch.object(score, 'atomic', side_effect=interrupt), self.assertRaises(OSError):
            music_update.apply(self.game, self.stage)
        with patch.object(router_update, 'require_closed'):
            self.assertEqual(music_update.apply(self.game, self.stage), 'applied')
        self.assertEqual((self.game/self.paths[0]).read_bytes(), (self.game/self.paths[1]).read_bytes())

    def test_uninstall_recovers_interrupted_update(self):
        real_atomic = score.atomic
        def interrupt(path, data):
            real_atomic(path, data)
            if path == self.game/self.paths[0]:
                raise OSError('interrupted')
        with patch.object(router_update, 'require_closed'), patch.object(score, 'atomic', side_effect=interrupt), self.assertRaises(OSError):
            music_update.apply(self.game, self.stage)
        with patch.object(router_update, 'require_closed'):
            score.uninstall(self.game)
        for path in self.paths:
            self.assertEqual((self.game/path).read_bytes(), b'original owner ambience')

    def test_non_exploration_changes_need_full_rebuild(self):
        text = self.mapping.read_text().replace('exploration', 'boss')
        self.mapping.write_text(text)
        with self.assertRaises(ValueError):
            music_update.prepare(self.game, 'uw2_13', 'uw1_10', self.root/'boss-stage', self.mapping)


if __name__ == '__main__':
    unittest.main()
