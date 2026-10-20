"""Execute the emitted ASL subset with stateful playback, not just a policy copy.

This is an offline harness, not a substitute for Arx's actual script runtime.
"""
import json
import pathlib
import re
import sys
import tempfile
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import amb,combat,score

BASE = ('ON INIT {\r\n SET §fighting_amb 0\r\n ACCEPT\r\n}\r\n'
        'ON OUCH {\r\n SET §fighting_amb 1\r\n AMBIANCE -v 90 ambient_fight\r\n'
        ' TIMERambfight 1 10 GOTO AMBIANCE_FIGHT_END\r\n ACCEPT\r\n}\r\n'
        '>>AMBIANCE_FIGHT_END\r\n TIMERother 1 10 GOTO AMBIANCE_DOWN\r\n ACCEPT\r\n'
        '>>AMBIANCE_DOWN\r\n SET §fighting_amb 0\r\n ACCEPT\r\n').encode('latin1')
CONFIG={'enabled':True,'low_health_fraction':.3,'recovery_health_fraction':.4}

class AslHarness:
    def __init__(self,script):
        text=script.decode('latin1').split(combat.MARKER.decode())[1]
        self.lines=[s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith('//')]
        self.labels={s[2:]:i+1 for i,s in enumerate(self.lines) if s.startswith('>>')}
        self.vars={'§uwscore_state':0};self.playing=set();self.starts=[]
    def value(self,word):
        return self.vars[word] if word[0] in '§@^' else float(word)
    def step(self,life,maximum=100,fighting=1):
        self.vars.update({'^player_life':life,'^player_maxlife':maximum,'§fighting_amb':fighting})
        pc=1;budget=100
        while budget:
            budget-=1;line=self.lines[pc];pc+=1
            if line.startswith('>>') or line=='}':continue
            if line.startswith('IF '):
                match=re.fullmatch(r'IF \((\S+) (==|!=|<=|>=|>) (\S+)\) (.+)',line)
                if not match:raise AssertionError(line)
                left,op,right,cmd=match.groups();a=self.value(left);b=self.value(right)
                condition={'==':a==b,'!=':a!=b,'<=':a<=b,'>=':a>=b,'>':a>b}[op]
                if cmd=='{':
                    if not condition:
                        depth=1
                        while depth:
                            item=self.lines[pc];pc+=1
                            depth+=int(item.endswith('{'))-int(item=='}')
                    continue
                if not condition:continue
                line=cmd
            words=line.split();cmd=words[0]
            if cmd=='GOTO':pc=self.labels[words[1]]
            elif cmd=='SET':self.vars[words[1]]=self.value(words[2])
            elif cmd=='MUL':self.vars[words[1]]*=self.value(words[2])
            elif cmd=='AMBIANCE':
                cue=words[3]
                if words[2]=='0':self.playing.discard(cue)
                else:
                    if cue not in self.playing:self.starts.append(cue)
                    self.playing.add(cue)
            elif cmd=='ACCEPT':return
            else:raise AssertionError(line)
        raise AssertionError('Controller did not terminate')

class CombatTests(unittest.TestCase):
    def test_health_healing_hysteresis_and_lifetime(self):
        h=AslHarness(combat.append_controller(BASE,CONFIG))
        cases=[(90,1,combat.NORMAL),(30,1,combat.LOW),(31,1,combat.LOW),
               (39.9,1,combat.LOW),(40,1,combat.NORMAL),(35,1,combat.NORMAL),
               (29,1,combat.LOW),(20,0,None),(20,1,combat.LOW),(0,1,None)]
        for life,fighting,expected in cases:
            h.step(life,fighting=fighting)
            self.assertEqual(h.playing,{expected} if expected else set())
        h.step(5,maximum=0);self.assertFalse(h.playing)
    def test_max_health_scaling_and_restore_without_restarts(self):
        h=AslHarness(combat.append_controller(BASE,CONFIG))
        h.step(60,maximum=200);self.assertEqual(h.playing,{combat.LOW})
        for _ in range(5):h.step(65,maximum=200)
        self.assertEqual(h.starts,[combat.LOW])
        h.playing.clear() # a load with saved locals but no restored audio
        h.step(65,maximum=200);self.assertEqual(h.playing,{combat.LOW})
        h.step(80,maximum=200);self.assertEqual(h.playing,{combat.NORMAL})
    def test_exact_prefix_timers_and_no_npc_health_reads(self):
        result=combat.append_controller(BASE,CONFIG)
        self.assertEqual(result[:len(BASE)],BASE)
        for match in re.finditer(b'TIMER',BASE):self.assertEqual(result[match.start():match.start()+30],BASE[match.start():match.start()+30])
        tail=result[len(BASE):].decode('latin1').lower()
        self.assertNotRegex(tail,r'\btimer\w*\s')
        self.assertEqual(set(re.findall(r'\^\w+',tail)),{'^player_life','^player_maxlife'})
    def test_conflicts_and_bad_settings_rejected(self):
        for extra in (b'ON MAIN { ACCEPT }',b'SETMAINEVENT custom',b'SETEVENT MAIN OFF',combat.MARKER,b'\0'):
            with self.assertRaises(ValueError):combat.append_controller(BASE+extra,CONFIG)
        with self.assertRaises(ValueError):combat.append_controller(b'ON INIT { ACCEPT }',CONFIG)
        for low,recover in ((.4,.3),(0,.4),(.3,1.1),(float('nan'),.4)):
            with self.assertRaises(ValueError):combat.validate({**CONFIG,'low_health_fraction':low,'recovery_health_fraction':recover})
        self.assertEqual(combat.append_controller(BASE,{**CONFIG,'enabled':False}),BASE)
    def test_full_build_install_conflict_and_script_restoration(self):
        with tempfile.TemporaryDirectory() as t:
            root=pathlib.Path(t);original=root/'original';assets=root/'assets';assets.mkdir()
            game=root/'game';game.mkdir();script=game/combat.PLAYER_SCRIPT
            score.atomic(script,BASE)
            heartbeat=amb.Ambiance(0x01000003,[amb.music_track(0x01000003,'sfx/heartbeat.wav',.8)]).encode()
            score.atomic(original/'sfx/ambiance/ambient_fight.amb',heartbeat)
            for track in ('uw2_03','uw2_04'):(assets/(track+'.wav')).write_bytes(score.encode_wav(22050,b'\0'*440))
            mapping=root/'mapping.csv'
            mapping.write_text('enabled,ambiance,track,gain,replace_beds\n1,'+combat.NORMAL+',uw2_03,0.95,\n1,'+combat.LOW+',uw2_04,0.95,\n')
            settings=root/'combat.json';score.save_json(settings,CONFIG)
            payload=root/'payload';manifest=score.build(original,assets,payload,mapping,player_script=script,combat_config=settings)
            score.verify(payload)
            self.assertEqual((payload/'sfx/ambiance/ambient_fight.amb').read_bytes(),heartbeat)
            script.write_bytes(BASE+b'// owner edit')
            with self.assertRaises(ValueError):score.install(payload,game)
            self.assertFalse(score.state_path(game).exists())
            script.write_bytes(BASE);score.install(payload,game)
            self.assertTrue(script.read_bytes().startswith(BASE));self.assertNotEqual(script.read_bytes(),BASE)
            score.uninstall(game);self.assertEqual(script.read_bytes(),BASE)
            # Packed baseline: no loose original must be restored by deleting override.
            script.unlink();score.install(payload,game);score.uninstall(game)
            self.assertFalse(script.exists())

if __name__=='__main__':unittest.main()
