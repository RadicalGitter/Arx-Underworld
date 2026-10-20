"""Music-only arbitration and read-only NPC combat observers for native ASL.

Original timer positions never move. Audio calls use equal-width GOSUB slots;
their original command still executes verbatim in the appended relay.
"""
import hashlib
import math
import re
import combat
import amb
import struct
import json

MARKER=b'// UWSCORE MUSIC ROUTER v2'
VICTORY='ambient_uwscore_victory'


def tokens(data):
    # Token positions are byte positions (latin1), including quoted arguments.
    pattern=rb'//[^\r\n]*|/\*.*?\*/|"[^"\r\n]*"|[^\s{}()]+|[{}()]'
    return [(m.start(),m.end(),m.group().decode('latin1')) for m in re.finditer(pattern,data,re.S)
            if not m.group().startswith((b'//',b'/*'))]


def plain(data):
    return ' '.join(t[2] for t in tokens(data)).lower()


def music_name(index):return f'ambient_uwscore_m{index:03d}'


# Every music layer plays at one fixed channel volume: loudness is normalised in the samples
# at build time, so zone/script/combat volume requests (100, 80, 60, 90...) no longer make
# some pieces louder than others. Requests still decide *which* piece plays and when it stops.
MUSIC_VOLUME = 100

def standalone(path,gain):
    track=amb.music_track(0x01000003,path,gain)
    tail=bytearray(track.tail)
    struct.pack_into('<I',tail,1,amb.MASTER)
    struct.pack_into('<I',tail,1+8+8,0) # one sample per key, native looping/once
    return amb.Ambiance(0x01000003,[amb.Track(track.path_bytes,bytes(tail))]).encode()


def validate(config):
    combat.validate(config)
    for key,default,minimum,maximum in (
            ('threat_radius',2200,500,6000),('quiet_seconds',6,2,30),
            ('armed_quiet_seconds',10,2,60),('minimum_battle_seconds',3,0,30)):
        value=config.get(key,default)
        if type(value) is not int or not minimum<=value<=maximum:raise ValueError('Invalid '+key)
    if config.get('armed_quiet_seconds',10)<config.get('quiet_seconds',6):raise ValueError('Armed quiet period must not be shorter')
    for fallback in config.get('region_fallbacks',[]):
        if not re.fullmatch(r'ambient_[a-z0-9_]+',fallback.get('ambiance','')):
            raise ValueError('Invalid regional fallback cue')
        if not fallback.get('anchors') or any(not re.fullmatch(r'[a-z0-9_]+_[0-9]{4}',a) for a in fallback['anchors']):
            raise ValueError('Invalid regional fallback landmarks')
    return config


def wrap_audio(original,cues):
    """Change only static selected AMBIANCE calls; retain all original offsets."""
    ts=tokens(original);patches=[];tails=[];used=set();i=0
    events=[]
    for n,t in enumerate(ts):
        if t[2].lower()!='on' or n+2>=len(ts) or ts[n+2][2]!='{':continue
        depth=1;j=n+3
        while j<len(ts) and depth:
            depth+=int(ts[j][2]=='{')-int(ts[j][2]=='}');j+=1
        if not depth:events.append((t[0],ts[j-1][1],ts[j-2][2].lower()))
    while i<len(ts):
        start,end,word=ts[i];lower=word.lower();zone=False
        if lower=='zoneparam' and i+1<len(ts) and ts[i+1][2].lower()=='ambiance':
            zone=True;j=i+2
        elif lower=='ambiance' and (i==0 or ts[i-1][2].lower()!='zoneparam'):
            j=i+1
        else:i+=1;continue
        volume='100';once=False
        while j<len(ts) and ts[j][2].startswith('-'):
            option=ts[j][2].lower();j+=1
            if 'n' in option:once=True
            if 'v' in option:
                if j>=len(ts):raise ValueError('Missing audio volume')
                volume=ts[j][2];j+=1
        if j>=len(ts):raise ValueError('Missing audio name')
        name=ts[j][2].strip('"').lower();end=ts[j][1]
        if name not in cues and name not in ('kill','none'):
            i=j+1;continue
        # A named AMBIANCE label is not an audio call; tokenization keeps >>.
        index=cues.get(name,{}).get('id',0)
        label=f'UR{len(patches):04x}'
        call=('GOSUB '+label).encode()
        command=original[start:end]
        if len(call)>len(command):raise ValueError('Audio slot too short')
        if b'\n' in command or b'\r' in command:raise ValueError('Multiline audio call needs manual support')
        replacement=call+b' '*(len(command)-len(call))
        line_start=original.rfind(b'\n',0,start)+1
        line_end=original.find(b'\n',end)
        if line_end<0:line_end=len(original)
        prefix=original[line_start:start]
        callback=bool(re.search(rb'\btimer\w*\b',prefix,re.I))
        if callback and tokens(original[end:line_end]):
            raise ValueError('Audio timer with additional callback commands needs manual support')
        if not callback and re.search(rb'\b(speak|playanim|cine)\b',prefix,re.I):
            raise ValueError('Asynchronous audio continuation needs manual support')
        for event_start,event_end,last in events:
            if event_start<=start<event_end and last not in ('accept','refuse','return'):
                raise ValueError('Audio relay requires an explicit original event terminator')
        patches.append({'start':start,'before':command.decode('latin1'),'after':replacement.decode('latin1')})
        # Preserve the native environmental action and volume expression in
        # the same entity context; report only the new music-layer request.
        tails.append(f'>>{label}\n '+command.decode('latin1')+
                     f'\n SET @uwsc_event_volume {volume}\n SENDEVENT uwsc_cue PLAYER "{index} ~@uwsc_event_volume~ {int(once)}"\n '+('ACCEPT' if callback else 'RETURN')+'\n')
        used.add(name);i=j+1
    changed=bytearray(original)
    for patch in patches:
        s=patch['start'];raw=patch['after'].encode('latin1');changed[s:s+len(raw)]=raw
    return bytes(changed),patches,'\n'.join(tails),used


def observer(original,config):
    code=plain(original)
    if 'uwsc_' in code or 'uwscore' in code:raise ValueError('Already contains music observer')
    if re.search(r'\bon\s+uwsc_probe\b',code):raise ValueError('NPC observer conflict')
    radius=config.get('threat_radius',2200)
    tail=f'''
ON UWSC_PROBE {{
 IF (^SENDER != PLAYER) ACCEPT
 SET §uwsc_engaged 0
 IF (^target != PLAYER) ACCEPT
 IF (^realdist_player > {radius}) ACCEPT
 IF ("f" ISIN ^behavior) GOTO UWSC_REPORT_THREAT
 IF ("m" ISIN ^behavior) GOTO UWSC_REPORT_THREAT
 IF ("d" ISIN ^behavior) GOTO UWSC_REPORT_THREAT
 IF ("o" ISIN ^behavior) GOTO UWSC_REPORT_THREAT
 IF ("e" ISIN ^behavior) GOTO UWSC_REPORT_THREAT
 ACCEPT
}}
>>UWSC_REPORT_THREAT
 SET §uwsc_engaged 1
 SENDEVENT uwsc_threat PLAYER ""
 ACCEPT
'''
    death=not re.search(r'\bon\s+dead\s*\{',code)
    if death:
        tail+=f'''
ON DEAD {{
 IF (§uwsc_engaged != 1) ACCEPT
 SET §uwsc_engaged 0
 IF (^realdist_player > {radius}) ACCEPT
 SENDEVENT uwsc_defeat PLAYER ""
 ACCEPT
}}
'''
    return tail,death


def controller(original,config,cues,zones):
    validate(config);code=plain(original)
    if any(re.search(r'\bon\s+'+event+r'\b',code) for event in ('main','load','uwsc_threat','uwsc_defeat','uwsc_cue')):
        raise ValueError('Player controller event conflict')
    if 'uwscore' in code or 'uwsc_' in code or re.search(r'\bsetmainevent\b|\bsetevent\s+main\b',code):
        raise ValueError('Player main-event conflict')
    radius=config.get('threat_radius',2200);quiet=config.get('quiet_seconds',6)
    armed=config.get('armed_quiet_seconds',10);minimum=config.get('minimum_battle_seconds',3)
    low=config['low_health_fraction'];recover=config['recovery_health_fraction']
    normal=cues[combat.NORMAL]['id'];danger=cues[combat.LOW]['id'];victory=cues[VICTORY]['id']
    special=sorted((v for v in cues.values() if v['role'] in ('story','boss')),key=lambda v:(v['priority'],v['id']))
    pressure=cues.get('ambient_blackthing')
    fallbacks=config.get('region_fallbacks',[])
    for fallback in fallbacks:
        if fallback['ambiance'] not in cues or cues[fallback['ambiance']]['role']!='exploration':
            raise ValueError('Regional fallback needs an enabled exploration cue')
    # Region/story state lives in saved globals (# and &): Arx never saves the
    # player's own local script variables, so locals were lost on every load.
    revision=int(hashlib.sha256((json.dumps(cues,sort_keys=True)+'|globals-v1').encode()).hexdigest()[:7],16)
    tail=f'''
ON LOAD {{
 GOSUB UWSC_RESET
 ACCEPT
}}
ON RELOAD {{
 SET #uwsc_region 0
 SET #uwsc_zone_music -1
 GOSUB UWSC_CLEAR_EVENTS
 GOSUB UWSC_RESET
 ACCEPT
}}
>>UWSC_RESET
 IF (#uwsc_revision != {revision}) {{
  SET #uwsc_revision {revision}
  SET #uwsc_region 0
  SET #uwsc_zone_music -1
'''
    for v in special:tail+=f'  SET &uwsc_v{v["id"]} 0\n'
    tail+=f''' }}
 IF (#uwsc_encounter_revision != 1) {{
  SET #uwsc_encounter_revision 1
  GOSUB UWSC_CLEAR_EVENTS
 }}
 SET §uwsc_playing -1
 SET §uwsc_scan -1
 SET §uwsc_battle 0
 SET §uwsc_defeated 0
 SET §uwsc_fanfare_until 0
 SET §uwsc_health 0
 GOSUB UWSC_REGION_FALLBACK
 RETURN
>>UWSC_CLEAR_EVENTS
'''
    for v in special:
        tail+=f' SET &uwsc_v{v["id"]} 0\n SET #uwsc_until{v["id"]} 0\n'
    tail+=' RETURN\n>>UWSC_REGION_FALLBACK\n'
    for fallback in fallbacks:
        n=cues[fallback['ambiance']]['id']
        for anchor in fallback['anchors']:
            tail+=f''' IF (^dist_{anchor} < 1000000) {{
  SET #uwsc_region {n}
  SET &uwsc_region_volume 100
  RETURN
 }}
'''
    tail+=' RETURN\n'
    tail+=f'''
ON UWSC_THREAT {{
 IF (^player_life <= 0) ACCEPT
 SET §uwsc_last_threat ^gameseconds
 SET §uwsc_defeated 0
 SET §uwsc_fanfare_until 0
'''
    if pressure:
        n=pressure['id']
        tail+=f''' IF (&uwsc_v{n} > 0) {{
  SET #uwsc_until{n} ^gameseconds
  INC #uwsc_until{n} {armed}
 }}
'''
    tail+=f'''
 IF (§uwsc_battle == 1) ACCEPT
 SET §uwsc_battle 1
 SET §uwsc_battle_start ^gameseconds
 ACCEPT
}}
ON UWSC_DEFEAT {{
 IF (§uwsc_battle != 1) ACCEPT
 SET §uwsc_defeated 1
 ACCEPT
}}
ON MAIN {{
 IF (^player_life <= 0) GOTO UWSC_DEATH
 IF (§uwsc_scan != ^gameseconds) {{
  SET §uwsc_scan ^gameseconds
  SENDEVENT -nr uwsc_probe {radius} ""
 }}
 GOSUB UWSC_ZONE
 IF (§uwsc_battle == 1) {{
  SET @uwsc_quiet ^gameseconds
  DEC @uwsc_quiet §uwsc_last_threat
  SET @uwsc_grace {quiet}
  IF (^fighting == 1) SET @uwsc_grace {armed}
  IF (@uwsc_quiet >= @uwsc_grace) GOSUB UWSC_END_BATTLE
 }}
 SET §uwsc_desired #uwsc_region
 SET @uwsc_volume &uwsc_region_volume
'''
    # Story layers outrank exploration; combat outranks non-boss story layers.
    def select(v):
        n=v['id']
        return f''' IF (&uwsc_v{n} > 0) {{
  IF (#uwsc_until{n} > 0) {{
   IF (^gameseconds >= #uwsc_until{n}) SET &uwsc_v{n} 0
  }}
  IF (&uwsc_v{n} > 0) {{
   SET §uwsc_desired {n}
   SET @uwsc_volume &uwsc_v{n}
  }}
 }}
'''
    for v in special:
        if v['priority']<70:tail+=select(v)
    tail+=f''' IF (§uwsc_battle == 1) {{
  SET §uwsc_desired {normal}
  SET @uwsc_volume 90
 }}
'''
    for v in special:
        if v['priority']>=70:
            tail+=' IF (§uwsc_battle == 1) {\n'+select(v)+' }\n'
    tail+=f''' IF (§uwsc_battle == 1) {{
  SET @uwsc_threshold ^player_maxlife
  IF (§uwsc_health == 2) {{
   MUL @uwsc_threshold {recover:.8g}
   IF (^player_life >= @uwsc_threshold) SET §uwsc_health 1
  }}
  ELSE {{
   MUL @uwsc_threshold {low:.8g}
   IF (^player_life <= @uwsc_threshold) SET §uwsc_health 2
  }}
  IF (§uwsc_health == 2) {{
   SET §uwsc_desired {danger}
   SET @uwsc_volume 90
  }}
 }}
 IF (§uwsc_fanfare_until > ^gameseconds) {{
  SET §uwsc_desired {victory}
  SET @uwsc_volume 90
 }}
 GOTO UWSC_APPLY
}}
>>UWSC_DEATH
 SET §uwsc_battle 0
 SET §uwsc_defeated 0
 SET §uwsc_fanfare_until 0
 SET §uwsc_desired 0
 GOTO UWSC_APPLY
>>UWSC_END_BATTLE
 SET §uwsc_battle 0
 SET §uwsc_health 0
'''
    if pressure:tail+=f' SET &uwsc_v{pressure["id"]} 0\n'
    tail+=f'''
 SET @uwsc_duration ^gameseconds
 DEC @uwsc_duration §uwsc_battle_start
 IF (@uwsc_duration < {minimum}) RETURN
 IF (§uwsc_defeated != 1) RETURN
 IF (^camera != none) RETURN
 SET §uwsc_defeated 0
 SET §uwsc_fanfare_until ^gameseconds
 INC §uwsc_fanfare_until {math.ceil(cues[VICTORY]['duration'])}
 RETURN
>>UWSC_APPLY
 IF (§uwsc_playing == §uwsc_desired) GOTO UWSC_VOLUME
 GOSUB UWSC_STOP_MUSIC
 SET §uwsc_playing §uwsc_desired
'''
    for v in cues.values():
        n=v['id'];name=music_name(n)
        # Separate commands preserve once-only mode while setting volume on
        # 1.2.1, where the combined -vn spelling is not supported.
        play=f'AMBIANCE -n {name}\n  AMBIANCE -v {MUSIC_VOLUME} {name}' if v['role']=='victory' else f'AMBIANCE -v {MUSIC_VOLUME} {name}'
        tail+=f' IF (§uwsc_desired == {n}) {{\n  {play}\n  ACCEPT\n }}\n'
    tail+=' ACCEPT\n>>UWSC_VOLUME\n'
    for v in cues.values():
        if v['role']!='victory':tail+=f' IF (§uwsc_desired == {v["id"]}) AMBIANCE -v {MUSIC_VOLUME} {music_name(v["id"])}\n'
    tail+=' ACCEPT\n>>UWSC_STOP_MUSIC\n'
    for name in [combat.NORMAL,combat.LOW,*[music_name(v['id']) for v in cues.values()]]:
        tail+=f' AMBIANCE -v 0 {name}\n'
    tail+=' RETURN\n>>UWSC_ZONE\n'
    for z in zones:
        n=cues[z['ambiance']]['id'];anchors=z.get('anchors',[])
        tail+=f' IF (^player_zone == "{z["zone"].lower()}") {{\n'
        if anchors:
            tail+='  SET §uwsc_area_match 0\n'
            for anchor in anchors:tail+=f'  IF (^dist_{anchor} < 1000000) SET §uwsc_area_match 1\n'
            tail+='  IF (§uwsc_area_match == 1) {\n'
        tail+=f'  IF (#uwsc_zone_music != {n}) {{\n   SET #uwsc_zone_music {n}\n'
        if cues[z['ambiance']]['role']=='boss':
            tail+=f'   SET &uwsc_v{n} {z["volume"]:.8g}\n'
        else:
            tail+=f'   SET #uwsc_region {n}\n   SET &uwsc_region_volume {z["volume"]:.8g}\n'
        tail+='  }\n'
        if anchors:tail+='  }\n'
        tail+=' }\n'
    tail+=' RETURN\nON UWSC_CUE {\n'
    # Regional script cues change the current background identity; other cues
    # retain independently stoppable requests until their original stop event.
    tail+=' IF (^#PARAM1 == 0) {\n  SET #uwsc_region 0\n'
    for v in special:tail+=f'  SET &uwsc_v{v["id"]} 0\n'
    tail+='  ACCEPT\n }\n'
    for v in cues.values():
        n=v['id']
        if v['role']=='exploration':
            tail+=f''' IF (^#PARAM1 == {n}) {{
  IF (^#PARAM2 > 0) {{
   SET #uwsc_region {n}
   SET &uwsc_region_volume ^#PARAM2
  }}
  ELSE {{
   IF (#uwsc_region == {n}) SET #uwsc_region 0
  }}
  ACCEPT
 }}
'''
        elif v['role'] in ('story','boss'):
            tail+=f''' IF (^#PARAM1 == {n}) {{
  SET &uwsc_v{n} ^#PARAM2
  SET #uwsc_until{n} 0
'''
            if pressure and n==pressure['id']:
                tail+=f''' IF (^#PARAM2 > 0) {{
  SET #uwsc_until{n} ^gameseconds
  INC #uwsc_until{n} {armed}
 }}
'''
            tail+=f'''
  IF (^#PARAM3 == 1) {{
   SET #uwsc_until{n} ^gameseconds
   INC #uwsc_until{n} {math.ceil(v['duration'])}
  }}
  ACCEPT
 }}
'''
    tail+=' ACCEPT\n}\n'
    return tail


def patch_script(original,cues,extra='',bootstrap=False):
    if MARKER in original or b'UWSCORE PLAYER HEALTH CONTROLLER' in original:
        raise ValueError('Build from unmodified baseline scripts')
    prefix,patches,relays,used=wrap_audio(original,cues)
    if bootstrap:
        match=re.search(rb'(?im)^[ \t]*on[ \t]+game_ready[ \t]*\{[ \t]*\r?\n[ \t]*([^\r\n]+)',original)
        if not match or b'ambient_fight' not in match[1].lower() or not match[1].lower().startswith(b'if '):
            raise ValueError('Unsupported player GAME_READY bootstrap; refusing to shift script offsets')
        start,end=match.span(1);before=original[start:end]
        after=b'GOSUB URBOOT'+b' '*(len(before)-len(b'GOSUB URBOOT'))
        changed=bytearray(prefix);changed[start:end]=after;prefix=bytes(changed)
        patches.append({'start':start,'before':before.decode('latin1'),'after':after.decode('latin1')})
        patches.sort(key=lambda p:p['start'])
        relays+='\n>>URBOOT\n GOSUB UWSC_RESET\n '+before.decode('latin1')+'\n RETURN\n'
    if not patches and not extra:return None
    suffix=b'\r\n'+MARKER+b'\r\n'+(relays+'\n'+extra).replace('\n','\r\n').encode('latin1')
    metadata={'original_bytes':len(original),'original_sha256':hashlib.sha256(original).hexdigest(),
              'replacements':patches,'appendix_sha256':hashlib.sha256(suffix).hexdigest()}
    return prefix+suffix,metadata,used


def verify_script(data,info):
    end=info['original_bytes'];prefix=bytearray(data[:end]);last=0
    for patch in info['replacements']:
        start=patch['start'];before=patch['before'].encode('latin1');after=patch['after'].encode('latin1')
        if start<last or len(before)!=len(after) or prefix[start:start+len(after)]!=after:raise ValueError('Invalid fixed-width audio patch')
        prefix[start:start+len(before)]=before;last=start+len(before)
    if hashlib.sha256(prefix).hexdigest()!=info['original_sha256']:raise ValueError('Original script bytes/offsets changed')
    if hashlib.sha256(data[end:]).hexdigest()!=info['appendix_sha256']:raise ValueError('Script appendix changed')
    return bytes(prefix)
