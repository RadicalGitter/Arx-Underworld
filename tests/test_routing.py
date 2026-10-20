"""Stateful execution of emitted routing ASL, with asynchronous event delivery.

The native engine is still required for final acceptance; this harness checks
the actual generated command flow rather than a duplicate combat policy.
"""
import collections
import pathlib
import re
import struct
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import combat,routing

CONFIG={'enabled':True,'low_health_fraction':.3,'recovery_health_fraction':.4,
        'threat_radius':2200,'quiet_seconds':6,'armed_quiet_seconds':10,'minimum_battle_seconds':3}
PLAN={'ambient_town':{'id':1,'role':'exploration','priority':10,'duration':100},
      combat.NORMAL:{'id':2,'role':'combat','priority':70,'duration':60},
      combat.LOW:{'id':3,'role':'combat','priority':90,'duration':60},
      routing.VICTORY:{'id':4,'role':'victory','priority':100,'duration':8},
      'ambient_fight_music':{'id':5,'role':'boss','priority':80,'duration':60},
      'ambient_dramatic':{'id':6,'role':'story','priority':60,'duration':4}}
ZONES=[{'zone':'town','ambiance':'ambient_town','volume':100,'anchors':['notice_0001']}]


class Entity:
    def __init__(self,world,name,code):
        self.world=world;self.name=name;self.vars={};self.dead=False
        self.system={'^target':'player','^behavior':'f','^realdist_player':100}
        self.lines=[s.strip() for s in code.splitlines() if s.strip() and not s.strip().startswith('//')]
        self.events={re.match(r'ON (\S+)',s,re.I)[1].lower():i+1 for i,s in enumerate(self.lines) if s.startswith('ON ')}
        self.labels={s[2:]:i+1 for i,s in enumerate(self.lines) if s.startswith('>>')}
    def value(self,word):
        if word.startswith('"'):return word.strip('"').lower()
        if word[0] in '§@£':return self.vars.get(word,'' if word[0]=='£' else 0)
        if word[0] in '#&$':return self.world.globals.get(word,'' if word[0]=='$' else 0)
        if word=='^gameseconds':return self.world.now
        if word.startswith('^'):
            return self.system.get(word,self.world.system.get(word,1e11 if word.startswith('^dist_') else 0))
        try:return float(word)
        except ValueError:return word.lower()
    def store(self,name):
        # Arx saves global (#, &, $) variables but never the player's locals.
        return self.world.globals if name[0] in '#&$' else self.vars
    def block_end(self,start):
        depth=1;i=start+1
        while depth:
            s=self.lines[i];depth+=int(s.endswith('{'))-int(s=='}');i+=1
        return i
    def run(self,event,sender='none',parameters=()):
        if event not in self.events:return
        if self.dead and event!='dead':return
        self.system['^SENDER']=sender
        for n in range(1,4):self.system['^#PARAM'+str(n)]=parameters[n-1] if n<=len(parameters) else 0
        pc=self.events[event];stack=[];budget=2000
        while budget:
            budget-=1;line=self.lines[pc];current=pc;pc+=1
            if line=='}' or line.startswith('>>'):continue
            if line=='ELSE {':pc=self.block_end(current);continue
            if line.startswith('IF '):
                match=re.fullmatch(r'IF \((\S+) (==|!=|<=|>=|>|<|ISIN) (\S+)\) (.+)',line)
                if not match:raise AssertionError(line)
                left,op,right,command=match.groups();a=self.value(left);b=self.value(right)
                if op=='ISIN':condition=str(a) in str(b)
                elif op=='==':condition=a==b
                elif op=='!=':condition=a!=b
                elif op=='<=':condition=a<=b
                elif op=='>=':condition=a>=b
                elif op=='>':condition=a>b
                else:condition=a<b
                if command=='{':
                    if not condition:
                        pc=self.block_end(current)
                        if pc<len(self.lines) and self.lines[pc]=='ELSE {':pc+=1
                    continue
                if not condition:continue
                line=command
            words=line.split();cmd=words[0]
            if cmd=='GOTO':pc=self.labels[words[1]]
            elif cmd=='GOSUB':stack.append(pc);pc=self.labels[words[1]]
            elif cmd=='RETURN':
                if not stack:raise AssertionError('RETURN without GOSUB')
                pc=stack.pop()
            elif cmd=='SET':self.store(words[1])[words[1]]=self.value(words[2])
            elif cmd in ('DEC','INC','MUL'):
                before=self.value(words[1]);amount=self.value(words[2])
                self.store(words[1])[words[1]]={'DEC':lambda:before-amount,'INC':lambda:before+amount,'MUL':lambda:before*amount}[cmd]()
            elif cmd=='AMBIANCE':
                name=words[-1]
                if words[1]=='-v' and self.value(words[2])==0:self.world.playing.discard(name)
                else:
                    if name not in self.world.playing:self.world.starts.append(name)
                    self.world.playing.add(name)
            elif cmd=='SENDEVENT':
                if words[1]=='-nr':
                    for name,target in self.world.npcs.items():
                        if target.system['^realdist_player']<=self.value(words[3]):self.world.queue.append((target,words[2],self.name,()))
                else:self.world.queue.append((self.world.player,words[1],self.name,()))
            elif cmd in ('ACCEPT','REFUSE'):return
            else:raise AssertionError(line)
        raise AssertionError('ASL instruction budget exhausted')


class World:
    def __init__(self):
        self.now=100;self.queue=collections.deque();self.playing=set();self.starts=[];self.globals={}
        self.system={'^player_life':100,'^player_maxlife':100,'^fighting':0,'^camera':'none','^player_zone':'town','^dist_notice_0001':200}
        self.code=routing.controller(b'ON INIT { ACCEPT }',CONFIG,PLAN,ZONES)
        self.player=Entity(self,'player',self.code)
        self.npcs={}
        self.player.run('load')  # GAME_READY at level start runs the reset
    def add(self,name='enemy'):
        self.npcs[name]=Entity(self,name,routing.observer(b'ON INIT { ACCEPT }',CONFIG)[0]);return self.npcs[name]
    def drain(self):
        while self.queue:
            entity,event,sender,params=self.queue.popleft();entity.run(event,sender,params)
    def step(self,now):
        self.now=now;self.player.run('main');self.drain();self.player.run('main');self.drain()
        if len(self.playing)>1:raise AssertionError('Music layers overlapped: '+repr(self.playing))
        return self.playing
    def load_save(self,saved_globals):
        # Save restoration: globals come from the save, the player's script
        # variables are not restored (fresh or stale), music restarts via reset.
        self.globals=dict(saved_globals);self.player=Entity(self,'player',self.code)
        self.playing=set();self.player.run('load');self.drain()
    def kill(self,name):
        npc=self.npcs[name];npc.dead=True;npc.run('dead');self.drain()
    def expect(self,test,index):test.assertEqual(self.playing,{routing.music_name(index)})


class RoutingTests(unittest.TestCase):
    def test_emitted_commands_use_native_arx_spellings(self):
        # Names checked against ScriptedLang/Variable/Control registrations.
        allowed={'SET','INC','DEC','MUL','GOTO','GOSUB','RETURN','ACCEPT','AMBIANCE','SENDEVENT'}
        for line in routing.controller(b'ON INIT { ACCEPT }',CONFIG,PLAN,ZONES).splitlines():
            line=line.strip()
            if not line or line.startswith(('ON ','>>','//')) or line in ('}','ELSE {'):continue
            if line.startswith('IF '):line=line.split(') ',1)[1]
            if line=='{':continue
            self.assertIn(line.split()[0],allowed,line)
    def test_start_before_damage_and_ignore_friendly_hazards(self):
        w=World();friend=w.add();friend.system['^behavior']='r';w.step(100);w.expect(self,1)
        w.player.vars['§fighting_amb']=1 # native damage latch alone is not combat
        w.system['^player_life']=60;w.step(101);w.expect(self,1)
        friend.system['^behavior']='fm';w.step(102);w.expect(self,2)
        self.assertEqual(w.system['^player_life'],60)
    def test_group_combat_and_one_victory_after_last_death(self):
        w=World();w.add('a');w.add('b');w.step(100);w.expect(self,2)
        w.kill('a');w.step(101);w.expect(self,2)
        w.step(102);w.kill('b');w.step(107);w.expect(self,2)
        w.step(108);w.expect(self,4)
        w.step(109);w.expect(self,4)
        w.step(116);w.expect(self,1)
        self.assertEqual(w.starts.count(routing.music_name(4)),1)
    def test_escape_and_death_have_no_fanfare(self):
        w=World();npc=w.add();w.step(100);npc.system['^target']='none'
        w.step(106);w.expect(self,1);self.assertNotIn(routing.music_name(4),w.starts)
        npc.system['^target']='player';w.step(107);w.system['^player_life']=0;w.step(108)
        self.assertFalse(w.playing);self.assertNotIn(routing.music_name(4),w.starts)
    def test_armed_grace_and_fanfare_interruption(self):
        w=World();w.add();w.system['^fighting']=1;w.step(100);w.kill('enemy')
        w.step(106);w.expect(self,2);w.step(110);w.expect(self,4)
        w.add('new');w.step(111);w.expect(self,2)
    def test_health_boss_priority_and_no_repeated_song_restart(self):
        w=World();w.add();w.step(100)
        w.player.run('uwsc_cue',parameters=(5,100,0));w.step(101);w.expect(self,5)
        w.system['^player_life']=30;w.step(102);w.expect(self,3)
        w.system['^player_life']=35;w.step(103);w.expect(self,3)
        w.system['^player_life']=40;w.step(104);w.expect(self,5)
        starts=len(w.starts);w.step(105);self.assertEqual(len(w.starts),starts)
    def test_story_once_expires_and_load_does_not_award_victory(self):
        w=World();w.step(100);w.player.run('uwsc_cue',parameters=(6,80,1))
        w.step(101);w.expect(self,6);w.step(104);w.expect(self,1)
        w.add();w.step(105);w.kill('enemy');w.player.run('load')
        w.step(120);w.expect(self,1);self.assertNotIn(routing.music_name(4),w.starts)
    def pressure_world(self):
        w=World()
        plan={**PLAN,'ambient_blackthing':{'id':7,'role':'story','priority':60,'duration':28}}
        w.code=routing.controller(b'ON INIT { ACCEPT }',CONFIG,plan,ZONES)
        w.player=Entity(w,'player',w.code);w.player.run('load');w.step(100)
        return w
    def test_teleport_clears_scripted_pressure_and_boss_without_victory(self):
        w=self.pressure_world();w.add();w.player.run('uwsc_cue',parameters=(7,100,0))
        w.player.run('uwsc_cue',parameters=(5,100,0));w.step(101);w.expect(self,5)
        w.kill('enemy');w.npcs.clear();w.player.run('reload');w.step(102)
        w.expect(self,1);self.assertNotIn(routing.music_name(4),w.starts)
        w.add('destination_enemy');w.step(103);w.expect(self,2)
    def test_unopposed_scripted_pressure_expires(self):
        w=self.pressure_world();w.player.run('uwsc_cue',parameters=(7,100,0))
        w.step(101);w.expect(self,7)
        w.step(110);w.expect(self,1)
    def test_pressure_refreshes_during_combat_and_stops_after_retreat(self):
        w=self.pressure_world();enemy=w.add();w.player.run('uwsc_cue',parameters=(7,100,0))
        for second in range(101,116):w.step(second)
        w.expect(self,2)
        self.assertGreater(w.globals['#uwsc_until7'],115)
        enemy.system['^target']='none';w.step(121);w.expect(self,1)
    def test_loading_save_preserves_current_pressure_but_migrates_old_leak(self):
        w=self.pressure_world();w.player.run('uwsc_cue',parameters=(7,100,0))
        saved=dict(w.globals);w.load_save(saved);w.step(101);w.expect(self,7)
        saved.pop('#uwsc_encounter_revision',None);w.load_save(saved);w.step(102)
        w.expect(self,1)
    def test_arx_fallback_recovers_city_music_outside_a_music_zone(self):
        config={**CONFIG,'region_fallbacks':[{'ambiance':'ambient_town','anchors':['city_notice_0001']}]}
        w=World();w.code=routing.controller(b'ON INIT { ACCEPT }',config,PLAN,ZONES)
        w.player=Entity(w,'player',w.code)
        w.system.update({'^player_zone':'teleporter','^dist_notice_0001':1e11,'^dist_city_notice_0001':100})
        w.globals.update({'#uwsc_region':999,'&uwsc_v6':100})
        w.player.run('reload');w.step(100);w.expect(self,1)
        w.load_save(dict(w.globals));w.step(101);w.expect(self,1)
        # An absent landmark must never identify an unrelated map as Arx.
        w.system['^dist_city_notice_0001']=1e11;w.player.run('reload');w.step(102)
        self.assertFalse(w.playing)
    def test_observers_read_no_npc_health_or_modify_gameplay(self):
        text,death=routing.observer(b'ON INIT { ACCEPT }',CONFIG);self.assertTrue(death)
        self.assertEqual(set(re.findall(r'\^\w+',text.lower())),{'^sender','^target','^realdist_player','^behavior'})
        self.assertNotRegex(text.lower(),r'\b(timer\w*|behavior|settarget|damage|destroy|heal)\s')
        _,death=routing.observer(b'ON DEAD { ACCEPT }',CONFIG);self.assertFalse(death)
    def test_fixed_width_audio_slots_and_reconstruction(self):
        source=b'ON TEST {\r\n TIMERabc 1 2 AMBIANCE -v 90 ambient_town\r\n IF (#x == 1) AMBIANCE -v 0 ambient_town ACCEPT\r\n ZONEPARAM AMBIANCE ambient_town\r\n AMBIANCE KILL\r\n ACCEPT\r\n}\r\n'
        result,info,used=routing.patch_script(source,PLAN)
        self.assertEqual(routing.verify_script(result,info),source)
        self.assertEqual(len(result[:len(source)]),len(source));self.assertEqual(len(info['replacements']),4)
        self.assertEqual(result.index(b'TIMERabc'),source.index(b'TIMERabc'))
        for patch in info['replacements']:self.assertIn(patch['before'].encode(),result[len(source):])
        self.assertEqual(used,{'ambient_town','kill'})
        self.assertRegex(result.decode('latin1'),r'>>UR0000\r\n[^>]*\r\n ACCEPT\r\n')
    def test_bootstrap_on_game_ready_preserves_offsets(self):
        original=('ON GAME_READY {\r\n IF (§fighting_amb == 0) AMBIANCE -v 0 ambient_fight\r\n'
                  ' TIMERnative 0 5 GOTO NATIVE\r\n ACCEPT\r\n}\r\n>>NATIVE\r\n ACCEPT\r\n').encode('latin1')
        extra=routing.controller(original,CONFIG,PLAN,ZONES)
        result,info,_=routing.patch_script(original,PLAN,extra,bootstrap=True)
        self.assertEqual(routing.verify_script(result,info),original)
        self.assertEqual(result.index(b'TIMERnative'),original.index(b'TIMERnative'))
        self.assertIn(b'GOSUB URBOOT',result[:len(original)])
        # The native player does not receive LOAD when reloading a save; its
        # existing GAME_READY handler must run the reset through this slot.
        self.assertIn(b'>>URBOOT\r\n GOSUB UWSC_RESET',result)
    def test_duplicate_zone_names_use_current_area_landmarks(self):
        w=World();plan={**PLAN,'ambient_other':{'id':7,'role':'exploration','priority':10,'duration':90}}
        zones=ZONES+[{'zone':'town','ambiance':'ambient_other','volume':100,'anchors':['notice_0002']}]
        w.player=Entity(w,'player',routing.controller(b'ON INIT { ACCEPT }',CONFIG,plan,zones))
        w.step(100);w.expect(self,1)
        w.system.update({'^dist_notice_0001':1e11,'^dist_notice_0002':100})
        w.step(101);w.expect(self,7)
    def test_region_survives_save_load_outside_trigger_zone(self):
        # Goblin city: music starts at the FIRETORCH gate zone; saves are made
        # deeper inside, where no routed zone is underfoot.
        w=World();w.step(100);w.expect(self,1)
        w.system['^player_zone']='city_interior';w.step(101);w.expect(self,1)
        saved=dict(w.globals);w.load_save(saved);w.step(102);w.expect(self,1)
    def test_loading_another_save_does_not_keep_stale_region(self):
        w=World();w.step(100);w.expect(self,1)
        w.system['^player_zone']='elsewhere';w.load_save({})
        w.step(101);self.assertEqual(w.playing,set())
    def test_save_without_state_recovers_at_next_routed_zone(self):
        w=World();w.system['^player_zone']='city_interior';w.load_save({})
        w.step(100);self.assertEqual(w.playing,set())
        w.system['^player_zone']='town';w.step(101);w.expect(self,1)
    def test_persistent_state_uses_saved_globals_only(self):
        text=routing.controller(b'ON INIT { ACCEPT }',CONFIG,PLAN,ZONES)
        for name in ('uwsc_region','uwsc_region_volume','uwsc_zone_music','uwsc_revision','uwsc_v5','uwsc_v6','uwsc_until6'):
            self.assertNotRegex(text,'[§@]'+name+r'\b')
            self.assertRegex(text,'[#&]'+name+r'\b')
    def test_music_only_ambiance_has_one_master_play_per_key(self):
        import amb
        result=amb.parse(routing.standalone('sfx/uwscore/victory.wav',.9))
        track=result.tracks[0];self.assertEqual(track.header(result.version),(4,1))
        self.assertEqual(struct.unpack_from('<I',track.tail,1+8+8)[0],0)

if __name__=='__main__':unittest.main()
