import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import combat
import routing
import router_update
import score
from test_routing import CONFIG, PLAN, ZONES


class RouterUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.game=self.root/'game';self.game.mkdir()
        self.baseline=('ON GAME_READY {\r\n IF (§fighting_amb == 0) AMBIANCE -v 0 ambient_fight\r\n'
                       ' ACCEPT\r\n}\r\n').encode('latin1')
        before,self.info,_=routing.patch_script(self.baseline,PLAN,'\nON LOAD { ACCEPT }\n',bootstrap=True)
        self.dest=score.safe_path(self.game,combat.PLAYER_SCRIPT);score.atomic(self.dest,before)
        backup=score.safe_path(self.game,'.uwscore-state/backups/'+combat.PLAYER_SCRIPT)
        score.atomic(backup,self.baseline)
        self.entry={'path':combat.PLAYER_SCRIPT,'original':score.sha(self.baseline),'installed':score.sha(before)}
        score.save_json(score.state_path(self.game),{'status':'installed','entries':[self.entry]})
        self.manifest=self.root/'manifest.json'
        score.save_json(self.manifest,{'files':{combat.PLAYER_SCRIPT:score.sha(before)},
              'script_patches':{combat.PLAYER_SCRIPT:self.info},'music_router':{'cues':PLAN,'zones':ZONES}})
        self.stage=self.root/'stage';router_update.prepare(self.game,self.manifest,self.stage)
    def test_apply_updates_only_player_and_retains_exact_uninstall(self):
        unrelated=self.game/'another-mod.txt';unrelated.write_bytes(b'owner changes')
        with patch.object(router_update,'require_closed'):
            self.assertEqual(router_update.apply(self.game,self.stage),'applied')
            self.assertEqual(router_update.apply(self.game,self.stage),'already applied')
        state=json.loads(score.state_path(self.game).read_text())
        self.assertEqual(state['entries'][0]['installed'],score.sha(self.dest.read_bytes()))
        self.assertEqual(routing.verify_script(self.dest.read_bytes(),state['router_patch']),self.baseline)
        self.assertEqual(unrelated.read_bytes(),b'owner changes')
        score.uninstall(self.game);self.assertEqual(self.dest.read_bytes(),self.baseline)
    def test_changed_player_is_rejected_without_overwrite(self):
        self.dest.write_bytes(b'new owner edit')
        with patch.object(router_update,'require_closed'),self.assertRaises(ValueError):
            router_update.apply(self.game,self.stage)
        self.assertEqual(self.dest.read_bytes(),b'new owner edit')
    def test_running_game_guard_prevents_writes(self):
        before=self.dest.read_bytes()
        with patch.object(router_update,'require_closed',side_effect=ValueError('running')),self.assertRaises(ValueError):
            router_update.apply(self.game,self.stage)
        self.assertEqual(self.dest.read_bytes(),before)
    def test_interruption_after_script_write_recovers_without_losing_uninstall(self):
        real_atomic=score.atomic
        def interrupt(path,data):
            real_atomic(path,data)
            if path==self.dest:raise OSError('simulated interruption')
        with patch.object(router_update,'require_closed'),patch.object(score,'atomic',side_effect=interrupt),self.assertRaises(OSError):
            router_update.apply(self.game,self.stage)
        state=router_update.recover(self.game)
        self.assertEqual(state['status'],'installed')
        self.assertEqual(state['entries'][0]['installed'],score.sha(self.dest.read_bytes()))
        score.uninstall(self.game);self.assertEqual(self.dest.read_bytes(),self.baseline)
    def test_interruption_before_script_write_recovers_original_installed_hash(self):
        state=json.loads(score.state_path(self.game).read_text())
        record=json.loads((self.stage/'router-update.json').read_text())
        state['status']='updating-router';state['pending_router_update']={k:record[k] for k in ('before','after','patch')}
        score.save_json(score.state_path(self.game),state)
        recovered=router_update.recover(self.game)
        self.assertEqual(recovered['entries'][0]['installed'],self.entry['installed'])


if __name__=='__main__':unittest.main()
