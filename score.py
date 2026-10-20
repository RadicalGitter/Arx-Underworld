"""Arx Underworld Music 0.2.0. Python 3.10+, standard library.
FFmpeg handles encoded imports and peak limiting; no downloads or game launches.
"""
import argparse
import array
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import datetime, timezone
import amb
import combat
import routing

ROOT = Path(__file__).resolve().parent
VERSION = '0.2.0'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.uwscore-tmp')
    with tmp.open('wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def save_json(path, data):
    atomic(path, (json.dumps(data, indent=2) + '\n').encode())

def safe_path(root, relative):
    # Reject alternate streams, absolute paths, traversal and directory links.
    if '\\' in relative or ':' in relative or relative.startswith('/'):
        raise ValueError('Unsafe relative path: ' + relative)
    parts = relative.split('/')
    if any(p in ('', '.', '..') for p in parts):
        raise ValueError('Unsafe relative path: ' + relative)
    path = root.joinpath(*parts)
    for p in [root, *[root.joinpath(*parts[:i]) for i in range(1, len(parts)+1)]]:
        if p.is_symlink() or (p.exists() and os.name == 'nt' and p.lstat().st_file_attributes & 0x400):
            raise ValueError('Refusing directory/file link: ' + str(p))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes root')
    return path

def allowed(relative):
    return ((relative.startswith('sfx/ambiance/') and relative.endswith('.amb')) or
            (relative.startswith('sfx/uwscore/') and relative.endswith('.wav')) or
            (relative.startswith('graph/obj3d/interactive/') and relative.endswith('.asl')))

def rows(mapping=ROOT/'mapping.csv'):
    with Path(mapping).open(encoding='utf-8-sig', newline='') as source:
        result = list(csv.DictReader(source))
    seen = set()
    for row in result:
        name = row['ambiance']
        if not name.startswith('ambient_') or not name.replace('_', '').isalnum() or name in seen:
            raise ValueError('Invalid/duplicate ambience: ' + name)
        seen.add(name)
        if row['enabled'] not in ('0', '1') or not 0 <= float(row['gain']) <= 1:
            raise ValueError('Invalid enabled/gain')
        if row['track'] and (not row['track'].replace('_', '').isalnum()):
            raise ValueError('Unsafe track ID')
    return result

def wav_info(data):
    with wave.open(io.BytesIO(data), 'rb') as f:
        if f.getcomptype() != 'NONE' or f.getsampwidth() != 2 or f.getnchannels() != 1:
            raise ValueError('Expected 16-bit mono PCM WAV')
        return f.getframerate(), f.getnframes(), f.readframes(f.getnframes())

def encode_wav(rate, pcm):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate); f.writeframes(pcm)
    return stream.getvalue()

def silence_like(path):
    # The native WAVs include ADPCM. Read the RIFF format/fact/data chunks to
    # derive duration without converting or copying their copyrighted sound.
    data = path.read_bytes()
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise ValueError('Invalid original WAV: ' + str(path))
    pos=12; fmt=None; frames=None; size=None
    while pos+8 <= len(data):
        kind=data[pos:pos+4]; length=int.from_bytes(data[pos+4:pos+8], 'little')
        block=data[pos+8:pos+8+length]
        if kind == b'fmt ': fmt=block
        if kind == b'fact' and length >= 4: frames=int.from_bytes(block[:4], 'little')
        if kind == b'data': size=length
        pos += 8+length+(length&1)
    if fmt is None or size is None: raise ValueError('WAV missing fmt/data')
    tag,channels,rate,byte_rate,align,bits=__import__('struct').unpack_from('<HHIIHH',fmt)
    # Arx's Microsoft ADPCM decoder derives its sample length from whole blocks.
    if tag == 1: frames=size//align
    elif tag == 2 and len(fmt) >= 20:
        samples_per_block=int.from_bytes(fmt[18:20], 'little')
        maximum=(size//align)*samples_per_block
        frames=min(frames if frames is not None else maximum,maximum)
    else: raise ValueError('Unsupported original WAV encoding')
    if not frames or frames > rate*3600: raise ValueError('Invalid original duration')
    return encode_wav(rate, b'\0' * frames * 2)

def normalize(data):
    rate, frames, pcm = wav_info(data)
    samples=array.array('h'); samples.frombytes(pcm)
    if sys.byteorder != 'little': samples.byteswap()
    if not samples: raise ValueError('Empty audio')
    peak=max(abs(x) for x in samples)
    rms=math.sqrt(sum(x*x for x in samples)/len(samples))
    factor=min(32767*10**(-3/20)/peak,32767*10**(-23/20)/rms) if peak else 1
    fade=min(int(rate*.6),len(samples)//4)
    for i,value in enumerate(samples):
        envelope=min(1,i/max(1,fade),(len(samples)-1-i)/max(1,fade))
        samples[i]=round(value*factor*envelope)
    if sys.byteorder != 'little': samples.byteswap()
    return encode_wav(rate,samples.tobytes())

def arx_volume_control(linear_gain):
    """Map desired sample amplitude to Arx's logarithmic volume control.

    At a full mixer OpenALSource::updateVolume computes 100000**control/100000.
    Passing 0.5 directly therefore attenuates by 50 dB, rather than 6 dB.
    Native script/zone and mixer controls still apply after this calibration.
    """
    if not math.isfinite(linear_gain) or not 0 <= linear_gain <= 1:
        raise ValueError('Linear gain outside [0,1]')
    return max(0.0,1.0+math.log10(linear_gain)/5.0) if linear_gain else 0.0

def arrange(data,clip_seconds=0,rest_seconds=0):
    rate,frames,pcm=wav_info(data)
    clip=float(clip_seconds);rest=float(rest_seconds)
    if not 0<=clip<=3600 or not 0<=rest<=3600:raise ValueError('Clip/rest duration outside [0,3600]')
    if clip and frames>int(clip*rate):
        samples=array.array('h');samples.frombytes(pcm[:int(clip*rate)*2])
        if sys.byteorder!='little':samples.byteswap()
        fade=min(rate,len(samples))
        for i in range(fade):samples[-fade+i]=round(samples[-fade+i]*(1-i/max(1,fade-1)))
        if sys.byteorder!='little':samples.byteswap()
        pcm=samples.tobytes()
    return encode_wav(rate,pcm+b'\0'*(round(rest*rate)*2))

def _limiter_delay(ffmpeg,rate,base,tmp):
    """Measure alimiter's uncompensated lookahead delay in samples at this rate."""
    mark=rate//10;probe=array.array('h',[0]*(rate//2));probe[mark]=8000
    if sys.byteorder!='little':probe.byteswap()
    src=tmp/'probe-in.wav';dst=tmp/'probe-out.wav';src.write_bytes(encode_wav(rate,probe.tobytes()))
    subprocess.run([str(ffmpeg),'-v','error','-nostdin','-y','-i',str(src),'-af',base,'-c:a','pcm_s16le',str(dst)],check=True,capture_output=True)
    _,_,pcm=wav_info(dst.read_bytes());out=array.array('h');out.frombytes(pcm)
    if sys.byteorder!='little':out.byteswap()
    hits=[i for i,v in enumerate(out) if abs(v)>1000]
    if not hits or not 0<=hits[0]-mark<rate//10:raise ValueError('Could not measure FFmpeg limiter delay')
    return hits[0]-mark

def boost_music(data,decibels,ffmpeg=None):
    """Boost only music, with a -1 dBFS sample-peak ceiling. Keep exact duration."""
    if not math.isfinite(decibels) or not 0 <= decibels <= 18:
        raise ValueError('Music boost must be between 0 and 18 dB')
    if not decibels:return data
    rate,frames,pcm=wav_info(data)
    samples=array.array('h');samples.frombytes(pcm)
    if sys.byteorder!='little':samples.byteswap()
    factor=10**(decibels/20);ceiling=10**(-1/20)
    peak=max((abs(v) for v in samples),default=0)
    if peak*factor <= 32767*ceiling:
        boosted=array.array('h',(round(v*factor) for v in samples))
        if sys.byteorder!='little':boosted.byteswap()
        return encode_wav(rate,boosted.tobytes())
    ffmpeg=ffmpeg or shutil.which('ffmpeg')
    if not ffmpeg:raise ValueError('FFmpeg is required to boost these music peaks safely; install it or set music_boost_db to 0 in mix.json')
    with tempfile.TemporaryDirectory(prefix='uwscore-limit-') as tmp:
        source=Path(tmp)/'in.wav';target=Path(tmp)/'out.wav';source.write_bytes(data)
        base=f'alimiter=level_in={factor:.12g}:level_out=1:limit={ceiling:.12g}:attack=5:release=50:level=false'
        run=lambda af:subprocess.run([str(ffmpeg),'-v','error','-nostdin','-y','-i',str(source),'-af',af,'-c:a','pcm_s16le',str(target)],capture_output=True,text=True)
        done=run(base+':latency=true')
        if done.returncode and 'latency' in (done.stderr or ''):
            # FFmpeg before 5.1 lacks latency compensation: measure the lookahead
            # delay, pad the tail by that amount and trim it from the start.
            delay=_limiter_delay(ffmpeg,rate,base,Path(tmp))
            done=run(f'apad=pad_len={delay},{base},atrim=start_sample={delay}:end_sample={delay+frames},asetpts=PTS-STARTPTS')
        if done.returncode:raise ValueError('FFmpeg limiter failed: '+(done.stderr or '').strip()[-400:])
        result=target.read_bytes()
    after_rate,after_frames,after_pcm=wav_info(result)
    if (after_rate,after_frames)!=(rate,frames):raise ValueError('Limiter changed music duration')
    checked=array.array('h');checked.frombytes(after_pcm)
    if sys.byteorder!='little':checked.byteswap()
    if max((abs(v) for v in checked),default=0)>math.ceil(32768*ceiling):raise ValueError('Limiter exceeded peak ceiling')
    return result

def gain_music(data,decibels,ffmpeg=None):
    """Apply a music gain: cuts are plain scaling; boosts reuse the -1 dBFS peak limiter."""
    if not math.isfinite(decibels) or not -40 <= decibels <= 18: raise ValueError('Music gain outside [-40,18] dB')
    if decibels >= 0: return boost_music(data,decibels,ffmpeg)
    rate,frames,pcm=wav_info(data)
    samples=array.array('h');samples.frombytes(pcm)
    if sys.byteorder!='little':samples.byteswap()
    factor=10**(decibels/20)
    scaled=array.array('h',(round(v*factor) for v in samples))
    if sys.byteorder!='little':scaled.byteswap()
    return encode_wav(rate,scaled.tobytes())

LOUDNESS_CACHE=ROOT/'.work'/'loudness-cache.json'

MUSIC_CACHE=ROOT/'.work'/'music-cache'

def music_cache_key(source,clip,rest,target):
    """Normalised music depends only on the source audio, its arrangement and the target."""
    return sha(f'{sha(source)}|{float(clip)}|{float(rest)}|{float(target)}|norm-v1'.encode())

def normalisation_gain(target,measured):
    """dB needed to bring a track to the target; near-silent audio (<= -60 LUFS, e.g. test
    pads or silence) is left alone, and gains are clamped to what gain_music supports."""
    if measured<=-60: return 0.0
    return max(-40.0,min(18.0,target-measured))

def integrated_loudness(data,ffmpeg=None):
    """EBU R128 integrated loudness (LUFS) of WAV bytes, measured with FFmpeg's ebur128 filter."""
    key=sha(data)
    try: cache=json.loads(LOUDNESS_CACHE.read_text())
    except (OSError,ValueError): cache={}
    if key in cache: return cache[key]
    ffmpeg=ffmpeg or shutil.which('ffmpeg')
    if not ffmpeg: raise ValueError('FFmpeg is required to measure music loudness')
    with tempfile.TemporaryDirectory(prefix='uwscore-lufs-') as tmp:
        src=Path(tmp)/'in.wav';src.write_bytes(data)
        out=subprocess.run([str(ffmpeg),'-hide_banner','-nostdin','-i',str(src),'-af','ebur128','-f','null','-'],capture_output=True,text=True)
    match=re.findall(r'I:\s*(-?[0-9.]+)\s*LUFS',out.stderr)
    if out.returncode or not match: raise ValueError('Could not measure loudness: '+out.stderr[-300:])
    value=float(match[-1])
    try:
        LOUDNESS_CACHE.parent.mkdir(exist_ok=True); cache[key]=value; LOUDNESS_CACHE.write_text(json.dumps(cache,indent=1))
    except OSError: pass
    return value

def load_mix():
    """mix.json: music_target_lufs (loudness every track is normalised to), environment_gain_db
    (uniform shift for environmental ambience tracks). Legacy music_boost_db is still read."""
    mix=json.loads((ROOT/'mix.json').read_text())
    if 'music_target_lufs' in mix:
        target=float(mix['music_target_lufs'])
        if not -36<=target<=-10: raise ValueError('music_target_lufs outside [-36,-10]')
    else: target=None
    env=float(mix.get('environment_gain_db',0))
    if not -30<=env<=0: raise ValueError('environment_gain_db outside [-30,0]')
    boost=float(mix.get('music_boost_db',0))
    if not math.isfinite(boost) or not 0<=boost<=18: raise ValueError('Music boost outside [0,18] dB')
    return {'target':target,'environment_db':env,'boost_db':boost}

def import_audio(source, destination, ffmpeg=None):
    source=Path(source); destination=Path(destination)
    if source.suffix.lower() in ('.xmi','.mid','.midi'):
        raise ValueError('Render MIDI/XMI with a synthesizer first; see docs/IMPORT.md')
    if source.resolve() == destination.resolve(): raise ValueError('Source and destination must differ')
    try:
        data=source.read_bytes(); rate,_,_=wav_info(data)
        if rate not in (22050,44100,48000): raise ValueError('Convert sample rate')
    except (ValueError,wave.Error,EOFError):
        ffmpeg=ffmpeg or shutil.which('ffmpeg')
        if not ffmpeg: raise ValueError('Install FFmpeg or supply 16-bit mono PCM WAV at 22050/44100/48000 Hz')
        with tempfile.TemporaryDirectory() as tmp:
            wav=Path(tmp)/'converted.wav'
            subprocess.run([str(ffmpeg),'-v','error','-nostdin','-y','-i',str(source),'-vn','-ac','1','-ar','22050','-c:a','pcm_s16le',str(wav)],check=True)
            data=wav.read_bytes()
    atomic(destination,normalize(data))

def placeholders(destination):
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    # Original mathematical pads, no melody, samples, MIDI or SoundFont inputs.
    for index,track in enumerate(sorted({r['track'] for r in rows() if r['track']})):
        rate=22050; duration=12; pcm=array.array('h')
        root=98*2**((index%12)/12)
        intervals=(0,7,12) if index%3 else (0,6,13)
        for n in range(rate*duration):
            t=n/rate
            env=min(1,t/1.5,(duration-t)/2)
            value=sum(math.sin(2*math.pi*root*2**(s/12)*t)/(j+2) for j,s in enumerate(intervals))
            pcm.append(round(2600*env*value*(.85+.15*math.cos(t*math.pi/3))))
        if sys.byteorder != 'little': pcm.byteswap()
        atomic(destination/(track+'.wav'),encode_wav(rate,pcm.tobytes()))
    print('Original test pads generated:', destination)

def case_file(root, relative):
    current=Path(root)
    for part in relative.replace('\\','/').split('/'):
        matches=[p for p in current.iterdir() if p.name.lower()==part.lower()]
        if len(matches)!=1: raise FileNotFoundError(relative)
        current=matches[0]
    return current

def extract(game, output, unpacker=None):
    game=Path(game); output=Path(output)
    if state_path(game).exists(): raise ValueError('Uninstall this mod before extracting its baseline')
    archive=case_file(game,'sfx.pak')
    exe=Path(unpacker) if unpacker else game/'arxunpak.exe'
    if not exe.is_file(): raise ValueError('Pass --unpacker pointing to Arx Libertatis arxunpak')
    output.mkdir(parents=True,exist_ok=True)
    # Explicit archive avoids extracting speech, textures or scripts.
    result=subprocess.run([str(exe.resolve()),'-e','-o',str(output.resolve()),'--',str(archive.resolve())],capture_output=True,text=True,errors='replace')
    atomic(output/'extract.log',(result.stdout+result.stderr).encode())
    if result.returncode: raise ValueError('arxunpak failed; see '+str(output/'extract.log'))
    if not (output/'sfx/ambiance/ambient_town.amb').is_file(): raise ValueError('Expected SFX resources missing')
    # Preserve an owner's loose audio overrides in the baseline too.
    try: loose=case_file(game,'sfx')
    except FileNotFoundError: loose=None
    if loose:
        for path in loose.rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.amb','.wav'):
                relative='sfx/'+path.relative_to(loose).as_posix().lower()
                atomic(safe_path(output,relative),path.read_bytes())
    if combat.validate(json.loads((ROOT/'combat.json').read_text()))['enabled']:
        extract_player(game,output,unpacker)
    print('Extracted owner game audio/player baseline to',output)

def extract_player(game, output, unpacker=None):
    """Copy the installed loose player script, or extract its archive baseline."""
    game=Path(game);output=Path(output)
    router=json.loads((ROOT/'combat.json').read_text()).get('music_router',False)
    try: loose=case_file(game,combat.PLAYER_SCRIPT)
    except FileNotFoundError: loose=None
    if loose and not router:
        atomic(safe_path(output,combat.PLAYER_SCRIPT),loose.read_bytes())
        return
    exe=Path(unpacker) if unpacker else game/'arxunpak.exe'
    if not exe.is_file():raise ValueError('Pass --unpacker to extract the packed player script')
    archives=[case_file(game,'data.pak')]
    try: archives.append(case_file(game,'data2.pak'))
    except FileNotFoundError: pass
    result=subprocess.run([str(exe.resolve()),'-e','-o',str(output.resolve()),'--',*[str(p.resolve()) for p in archives]],capture_output=True,text=True,errors='replace')
    atomic(output/'extract-player.log',(result.stdout+result.stderr).encode())
    if result.returncode:raise ValueError('Player extraction failed; see extract-player.log')
    try: interactive=case_file(game,'graph/obj3d/interactive')
    except FileNotFoundError: interactive=None
    if interactive:
        for path in interactive.rglob('*'):
            if path.is_file() and path.suffix.lower()=='.asl':
                relative='graph/obj3d/interactive/'+path.relative_to(interactive).as_posix().lower()
                atomic(safe_path(output,relative),path.read_bytes())
    case_file(output,combat.PLAYER_SCRIPT)

def build(original, assets, output, mapping=ROOT/'mapping.csv', gain_scale=1,keep_original_music=False,player_script=None,combat_config=ROOT/'combat.json'):
    original=Path(original); assets=Path(assets); output=Path(output)
    if output.exists() and any(output.iterdir()): raise ValueError('Build output must be empty; choose a new folder')
    table=[r for r in rows(mapping) if r['enabled']=='1']
    if not table: raise ValueError('No enabled cues')
    settings=combat.validate(json.loads(Path(combat_config).read_text()))
    router=settings.get('music_router',False) and settings['enabled']
    if router:routing.validate(settings)
    mix=load_mix(); boost_db=mix['boost_db']; env_db=mix['environment_db']
    adaptive=settings['enabled']
    custom={combat.NORMAL,combat.LOW,routing.VICTORY}
    if adaptive:
        if not ({combat.NORMAL,combat.LOW}|({routing.VICTORY} if router else set())) <= {r['ambiance'] for r in table}:
            raise ValueError('Adaptive combat needs both enabled custom combat mapping rows')
        if any(r['ambiance']=='ambient_fight' for r in table):
            raise ValueError('Disable ambient_fight music row when adaptive combat is enabled')
        script_source=Path(player_script) if player_script else case_file(original,combat.PLAYER_SCRIPT)
        script_before=script_source.read_bytes()
        script_after=None if router else combat.append_controller(script_before,settings)
        heartbeat=case_file(original,'sfx/ambiance/ambient_fight.amb').read_bytes()
        amb.parse(heartbeat)
    # Preflight all inputs before writing any output.
    selected=[]
    for r in table:
        synthetic=r['ambiance'] in custom
        if synthetic and not adaptive: continue
        source=None if synthetic else case_file(original,'sfx/ambiance/'+r['ambiance']+'.amb')
        data=b'' if synthetic else source.read_bytes()
        parsed=amb.Ambiance(0x01000003,[]) if synthetic else amb.parse(data)
        track=assets/(r['track']+'.wav'); wav_info(track.read_bytes())
        beds=[] if keep_original_music else [p.strip().lower() for p in r['replace_beds'].split(';') if p.strip()]
        for bed in beds:
            if bed not in {t.path for t in parsed.tracks}: raise ValueError('Expected bed absent: '+bed+' in '+source.name)
            case_file(original,bed)
        gain=float(r['gain'])*gain_scale
        if not 0<=gain<=1: raise ValueError('Gain outside [0,1]')
        selected.append((r,data,parsed,beds,gain))
    manifest={'version':VERSION,'kind':'arx-underworld-music','files':{},'cues':[], 'asset_hashes':{},'preconditions':{},
              'mix':{'music_target_lufs':mix['target'],'music_boost_db':None if mix['target'] is not None else boost_db,
                     'environment_gain_db':env_db,'sample_peak_ceiling_dbfs':-1,'track_loudness_lufs':{}}}
    plan={};next_id=1
    def write(relative,data):
        if not allowed(relative): raise ValueError('Unexpected payload path')
        atomic(safe_path(output,relative),data); manifest['files'][relative]=sha(data)
    for r,data,parsed,beds,gain in selected:
        anchors={}
        for bed in beds:
            anchor='sfx/uwscore/anchor_'+sha(bed.encode())[:12]+'.wav'
            if anchor not in manifest['files']: write(anchor,silence_like(case_file(original,bed)))
            anchors[bed]=anchor
        clip=float(r.get('clip_seconds',0));rest=float(r.get('rest_seconds',0))
        arrangement=sha(f'{clip}:{rest}'.encode())[:8]
        music='sfx/uwscore/'+r['track']+'_'+arrangement+'.wav'
        if music not in manifest['files']:
            source_audio=(assets/(r['track']+'.wav')).read_bytes()
            if mix['target'] is not None:
                measured=integrated_loudness(source_audio); manifest['mix']['track_loudness_lufs'][r['track']]=measured
                key=music_cache_key(source_audio,clip,rest,mix['target']); cached=MUSIC_CACHE/(key+'.wav')
                if cached.is_file(): rendered=cached.read_bytes()
                else:
                    rendered=gain_music(arrange(source_audio,clip,rest),normalisation_gain(mix['target'],measured))
                    try: MUSIC_CACHE.mkdir(parents=True,exist_ok=True); atomic(cached,rendered)
                    except OSError: pass
                write(music,rendered)
            else:
                write(music,boost_music(arrange(source_audio,clip,rest),boost_db))
        native_gain=arx_volume_control(gain)
        managed=router and r['ambiance']!='ambient_menu'
        music_ambiance=None
        if managed:
            music_ambiance=routing.music_name(next_id)
            rate,frames,_=wav_info((output/music).read_bytes())
            plan[r['ambiance']]={'id':next_id,'role':r.get('role') or 'exploration','priority':int(r.get('priority') or 10),'duration':frames/rate}
            next_id+=1
            write('sfx/ambiance/'+music_ambiance+'.amb',routing.standalone(music,native_gain))
            result=(amb.Ambiance(parsed.version,[t.with_path(anchors[t.path]) if t.path in anchors else amb.scale_volume(t,parsed.version,env_db) for t in parsed.tracks]).encode() if data else None)
        else:
            result=(amb.Ambiance(parsed.version,[amb.music_track(parsed.version,music,native_gain)]).encode()
                    if not data else amb.patch(data,music,native_gain,anchors,env_db))
        if result is not None:
            after=amb.parse(result)
            for before,new in zip(parsed.tracks,after.tracks):
                if before.path not in anchors and amb.without_volumes(before,parsed.version)!=amb.without_volumes(new,parsed.version): raise AssertionError('Environment changed beyond volume')
                if amb.without_volumes(before,parsed.version)[len(before.path_bytes):]!=amb.without_volumes(new,parsed.version)[len(new.path_bytes):]: raise AssertionError('Original schedule changed')
            write('sfx/ambiance/'+r['ambiance']+'.amb',result)
        manifest['cues'].append({'ambiance':r['ambiance'],'music_ambiance':music_ambiance,'track':r['track'],'synthetic':not bool(data),'input_sha256':sha(data) if data else None,'preserved_environment_tracks':len(parsed.tracks)-len(beds),'silent_anchors':anchors,'gain':gain,'native_volume_control':native_gain,'clip_seconds':clip,'rest_seconds':rest})
    if adaptive:
        write('sfx/ambiance/ambient_fight.amb',heartbeat)
        if router:
            zones=json.loads((ROOT/'docs/zone-music.json').read_text())
            zones=[z for z in zones if z['ambiance'] in plan]
            script_patches={};observers=[];used=set()
            sources={f.relative_to(original).as_posix().lower():f.read_bytes() for f in (original/'graph/obj3d/interactive').rglob('*.asl')}
            sources[combat.PLAYER_SCRIPT]=script_before
            if not any(repr_name.startswith('graph/obj3d/interactive/npc/') for repr_name in sources):raise ValueError('Extract the complete script baseline for music routing')
            for relative,baseline in sorted(sources.items()):
                extra=''
                if relative==combat.PLAYER_SCRIPT:extra=routing.controller(baseline,settings,plan,zones)
                elif relative.startswith('graph/obj3d/interactive/npc/') and len(relative.split('/'))==6:
                    extra,death=routing.observer(baseline,settings);observers.append({'path':relative,'death_event':death})
                patch=routing.patch_script(baseline,plan,extra,bootstrap=relative==combat.PLAYER_SCRIPT)
                if patch:
                    data,info,observed=patch;write(relative,data);script_patches[relative]=info
                    manifest['preconditions'][relative]=sha(baseline);used|=observed
            manifest['script_patches']=script_patches
            manifest['music_router']={'settings':settings,'cues':plan,'zones':zones,'npc_observers':observers,'wrapped_native_cues':sorted(used),'npc_health_used':False,'new_timers':False}
            # Old saves can refer to the v0.1.4/5 ordinary AMBs. Keep silent
            # resources so loading them doesn't emit missing-resource errors.
            silent='sfx/uwscore/legacy_silence.wav'
            write(silent,encode_wav(22050,b'\0'*44100))
            for name in (combat.NORMAL,combat.LOW):write('sfx/ambiance/'+name+'.amb',routing.standalone(silent,0))
        else:
            write(combat.PLAYER_SCRIPT,script_after)
            manifest['preconditions'][combat.PLAYER_SCRIPT]=sha(script_before)
            manifest['player_health_combat']={**settings,'original_script_bytes':len(script_before),'original_script_sha256':sha(script_before),'appendix_sha256':sha(script_after[len(script_before):]),'npc_health_used':False,'new_timers':False}
    save_json(output/'mod-manifest.json',manifest)
    print(f'Built {len(selected)} cues, {len(manifest["files"])} payload files:',output)
    return manifest

def verify(payload):
    payload=Path(payload); manifest=json.loads((payload/'mod-manifest.json').read_text())
    if manifest.get('kind')!='arx-underworld-music': raise ValueError('Wrong manifest kind')
    for relative,info in manifest.get('script_patches',{}).items():
        if relative not in manifest['files'] or manifest.get('preconditions',{}).get(relative)!=info['original_sha256']:
            raise ValueError('Missing script baseline/precondition: '+relative)
    if manifest.get('music_router'):
        routing.validate(manifest['music_router']['settings'])
        for cue in manifest['music_router']['cues'].values():
            if 'sfx/ambiance/'+routing.music_name(cue['id'])+'.amb' not in manifest['files']:
                raise ValueError('Missing routed music resource')
    if manifest.get('player_health_combat'):
        info=combat.validate(manifest['player_health_combat'])
        required={combat.PLAYER_SCRIPT,'sfx/ambiance/ambient_fight.amb',
                  'sfx/ambiance/'+combat.NORMAL+'.amb','sfx/ambiance/'+combat.LOW+'.amb'}
        if not required <= manifest['files'].keys():raise ValueError('Incomplete adaptive combat payload')
        if manifest.get('preconditions',{}).get(combat.PLAYER_SCRIPT)!=info['original_script_sha256']:
            raise ValueError('Missing player baseline precondition')
    for relative,digest in manifest['files'].items():
        if not allowed(relative): raise ValueError('Disallowed payload path')
        path=safe_path(payload,relative)
        data=path.read_bytes()
        if sha(data)!=digest: raise ValueError('Payload changed: '+relative)
        if relative.endswith('.amb'):
            parsed=amb.parse(data)
            for t in parsed.tracks:
                if t.path.startswith('sfx/uwscore/') and t.path not in manifest['files']: raise ValueError('Missing bundled sample')
        elif relative in manifest.get('script_patches',{}):
            routing.verify_script(data,manifest['script_patches'][relative])
        elif relative == combat.PLAYER_SCRIPT:
            info=manifest.get('player_health_combat',{})
            prefix=data[:info.get('original_script_bytes',0)]
            if sha(prefix)!=info.get('original_script_sha256') or combat.append_controller(prefix,info)!=data:
                raise ValueError('Player script is not the exact approved appendix over its baseline')
        elif relative.endswith('.asl'):raise ValueError('Script missing reconstruction metadata')
        else: wav_info(data)
    return manifest

def import_library(source,assets,manifest=ROOT/'import.csv',ffmpeg=None):
    source=Path(source).resolve(); assets=Path(assets)
    table=list(csv.DictReader(Path(manifest).open(encoding='utf-8-sig',newline='')))
    known={r['track'] for r in rows()}; seen=set(); planned=[]
    for r in table:
        track=r['track_id']
        if track not in known or track in seen: raise ValueError('Unknown/duplicate track in import.csv')
        seen.add(track)
        path=safe_path(source,r['source'])
        if not path.is_file(): raise FileNotFoundError(path)
        planned.append((track,path))
    required={r['track'] for r in rows() if r['enabled']=='1'}
    if not required<=seen: raise ValueError('Import manifest missing enabled track IDs')
    for track,path in planned:
        import_audio(path,assets/(track+'.wav'),ffmpeg)
        print('Imported',track)
    save_json(assets/'asset-provenance.json',{'mode':'owner-provided rendered audio','sources':[{'track':t,'source_name':p.name,'source_sha256':sha(p.read_bytes()),'output_sha256':sha((assets/(t+'.wav')).read_bytes())} for t,p in planned]})

def render_xmi(uw1,uw2,renderer,assets,bank_uw1='51',bank_uw2='50'):
    """Offline FM rendition, not an authentic MT-32 recording. No assets bundled.

    Uses the owner's XMI and an external libADLMIDI command-line renderer.
    Intermediate XMI/WAV files stay private. The original game stays read-only.
    """
    renderer=Path(renderer).resolve();assets=Path(assets).resolve()
    fingerprint=sha(renderer.read_bytes())
    banks=subprocess.run([str(renderer),'--list-banks'],capture_output=True,text=True,errors='replace',timeout=20)
    if bank_uw1=='51' and not __import__('re').search(r'51\s*=\s*AIL \(FatMan MT32\)',banks.stdout):
        raise ValueError('Renderer bank 51 differs; choose --bank-uw1 explicitly as a WOPL path')
    if bank_uw2=='50' and not __import__('re').search(r'50\s*=\s*AIL \(Ultima Underworld 2\)',banks.stdout):
        raise ValueError('Renderer bank 50 differs; choose --bank-uw2 explicitly as a WOPL path')
    roots={'uw1':Path(uw1),'uw2':Path(uw2)}
    inputs=[]
    for track in sorted({r['track'] for r in rows() if r['track']}):
        game,number=track.split('_');name=('UW' if game=='uw1' else 'UWR')+number+'.XMI'
        path=case_file(roots[game],name);bank=bank_uw1 if game=='uw1' else bank_uw2
        if not str(bank).isdigit():bank=str(Path(bank).resolve())
        inputs.append((track,path,bank))
    assets.mkdir(parents=True,exist_ok=True)
    provenance_path=assets/'xmi-provenance.json'
    previous=json.loads(provenance_path.read_text()) if provenance_path.exists() else {'tracks':{}}
    provenance={'mode':'offline FM rendition; not authentic MT-32','renderer_sha256':fingerprint,'tracks':dict(previous['tracks'])}
    private=assets.parent/('xmi-render-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    private.mkdir(parents=True)
    for track,path,bank in inputs:
        identity={'source_sha256':sha(path.read_bytes()),'renderer_sha256':fingerprint,'bank':bank,'bank_sha256':sha(Path(bank).read_bytes()) if not bank.isdigit() else None,'render_gain':0.5,'recipe_revision':2}
        output=assets/(track+'.wav');prior=previous['tracks'].get(track,{})
        if output.exists() and all(prior.get(k)==v for k,v in identity.items()) and prior.get('output_sha256')==sha(output.read_bytes()):
            print('Already rendered',track,flush=True);continue
        copied=private/(track+'.xmi');copied.write_bytes(path.read_bytes())
        command=[str(renderer),str(copied),'-w','-nl','-mono','-s16','--gain','0.5',bank,'1']
        with (private/(track+'.log')).open('w',encoding='utf-8') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        wav=copied.with_suffix('.xmi.wav')
        if not wav.is_file():raise ValueError('Renderer did not produce expected WAV; see '+str(private))
        import_audio(wav,output)
        provenance['tracks'][track]={**identity,'output_sha256':sha(output.read_bytes())}
        save_json(provenance_path,provenance)
        print('Rendered',track,flush=True)
    print('Private rendered library:',assets)

def setup(game,mode='test',assets=None,unpacker=None):
    # Private, unique staging makes interrupted setup safe to rerun.
    staging=ROOT/'.work'/('setup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    staging.mkdir(parents=True)
    extract(game,staging/'original',unpacker)
    library=ROOT/'placeholders' if mode=='test' else Path(assets or ROOT/'assets')
    manifest=build(staging/'original',library,staging/'payload')
    verify(staging/'payload'); install(staging/'payload',game)
    print('Private build and receipt:',staging)

def state_path(game):
    return safe_path(Path(game),'.uwscore-state/state.json')

def install(payload,game,dry_run=False):
    payload=Path(payload); game=Path(game).resolve(); manifest=verify(payload)
    # Deliberately require an explicit target. No registry/Steam discovery writes.
    if not game.is_dir(): raise ValueError('Game directory does not exist')
    state=state_path(game)
    if state.exists(): raise ValueError('Existing installation/journal: uninstall it first')
    entries=[]
    for relative,digest in manifest['files'].items():
        dest=safe_path(game,relative)
        expected=manifest.get('preconditions',{}).get(relative)
        if expected and dest.exists() and sha(dest.read_bytes())!=expected:
            raise ValueError('Script differs from build baseline; rebuild from current files: '+relative)
        entries.append({'path':relative,'installed':digest,'original':sha(dest.read_bytes()) if dest.exists() else None})
    if dry_run:
        print(f'Would install {len(entries)} files; back up {sum(e["original"] is not None for e in entries)} existing files.'); return
    # All backups are durable before the journal authorizes the first mutation.
    for e in entries:
        if e['original']:
            data=safe_path(game,e['path']).read_bytes()
            atomic(safe_path(game,'.uwscore-state/backups/'+e['path']),data)
            if sha(data)!=e['original']: raise ValueError('Target changed during backup')
    record={'status':'installing','version':manifest.get('version',VERSION),'entries':entries}
    save_json(state,record)
    for e in entries:
        dest=safe_path(game,e['path'])
        current=sha(dest.read_bytes()) if dest.exists() else None
        if current!=e['original']: raise ValueError('Target changed during install; journal preserved for recovery')
        data=safe_path(payload,e['path']).read_bytes()
        if sha(data)!=e['installed']: raise ValueError('Payload changed during install; journal preserved')
        atomic(dest,data)
    record['status']='installed'; save_json(state,record)
    print('Installed. Restart Arx Libertatis to load changed audio/scripts. Uninstall with this tool.')

def uninstall(game):
    game=Path(game).resolve(); state=state_path(game)
    record=json.loads(state.read_text()); entries=record['entries']
    if record.get('pending_router_update'):
        import router_update
        router_update.require_closed()
        record=router_update.recover(game); entries=record['entries']
    # Validate every path and preimage before making ANY change. An interrupted
    # install/uninstall is safe to rerun while current files match either image.
    for e in entries:
        if not allowed(e['path']): raise ValueError('Invalid journal path')
        dest=safe_path(game,e['path']); current=sha(dest.read_bytes()) if dest.exists() else None
        if current not in (e['installed'],e['original']): raise ValueError('Locally changed file; preserve/resolve before uninstall: '+e['path'])
        if e['original']:
            backup=safe_path(game,'.uwscore-state/backups/'+e['path'])
            if sha(backup.read_bytes())!=e['original']: raise ValueError('Backup checksum failed')
    record['status']='uninstalling'; save_json(state,record)
    for e in entries:
        dest=safe_path(game,e['path'])
        if e['original']: atomic(dest,safe_path(game,'.uwscore-state/backups/'+e['path']).read_bytes())
        elif dest.exists(): dest.unlink()
    # Keep a receipt/backups. Only the active journal name is released.
    receipt=state.with_name('removed-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json')
    os.replace(state,receipt)
    print('Restored previous audio and any patched player script. Saves, maps and settings were untouched.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('placeholders'); p.add_argument('--output',type=Path,default=ROOT/'placeholders')
    p=sub.add_parser('extract'); p.add_argument('--game-dir',required=True,type=Path); p.add_argument('--output',required=True,type=Path); p.add_argument('--unpacker')
    p=sub.add_parser('import'); p.add_argument('--source',required=True,type=Path); p.add_argument('--track',required=True); p.add_argument('--assets',type=Path,default=ROOT/'assets'); p.add_argument('--ffmpeg')
    p=sub.add_parser('import-library'); p.add_argument('--source',required=True,type=Path); p.add_argument('--assets',type=Path,default=ROOT/'assets'); p.add_argument('--manifest',type=Path,default=ROOT/'import.csv'); p.add_argument('--ffmpeg')
    p=sub.add_parser('render-xmi'); p.add_argument('--uw1-sound',required=True,type=Path); p.add_argument('--uw2-sound',required=True,type=Path); p.add_argument('--renderer',required=True,type=Path); p.add_argument('--assets',required=True,type=Path); p.add_argument('--bank-uw1',default='51'); p.add_argument('--bank-uw2',default='50')
    p=sub.add_parser('setup'); p.add_argument('--game-dir',required=True,type=Path); p.add_argument('--mode',choices=['test','underworld'],default='test'); p.add_argument('--assets',type=Path); p.add_argument('--unpacker')
    p=sub.add_parser('build'); p.add_argument('--original',required=True,type=Path); p.add_argument('--assets',required=True,type=Path); p.add_argument('--output',required=True,type=Path); p.add_argument('--mapping',type=Path,default=ROOT/'mapping.csv'); p.add_argument('--gain-scale',type=float,default=1); p.add_argument('--keep-original-music',action='store_true'); p.add_argument('--player-script',type=Path); p.add_argument('--combat-config',type=Path,default=ROOT/'combat.json')
    p=sub.add_parser('verify'); p.add_argument('--payload',required=True,type=Path)
    p=sub.add_parser('install'); p.add_argument('--payload',required=True,type=Path); p.add_argument('--game-dir',required=True,type=Path); p.add_argument('--dry-run',action='store_true')
    p=sub.add_parser('uninstall'); p.add_argument('--game-dir',required=True,type=Path)
    args=parser.parse_args()
    try:
        if args.action=='placeholders': placeholders(args.output)
        elif args.action=='extract': extract(args.game_dir,args.output,args.unpacker)
        elif args.action=='import':
            known={r['track'] for r in rows()}
            if args.track not in known: raise ValueError('Unknown track ID; see mapping.csv')
            import_audio(args.source,args.assets/(args.track+'.wav'),args.ffmpeg); print('Imported',args.track)
        elif args.action=='import-library': import_library(args.source,args.assets,args.manifest,args.ffmpeg)
        elif args.action=='render-xmi': render_xmi(args.uw1_sound,args.uw2_sound,args.renderer,args.assets,args.bank_uw1,args.bank_uw2)
        elif args.action=='setup': setup(args.game_dir,args.mode,args.assets,args.unpacker)
        elif args.action=='build': build(args.original,args.assets,args.output,args.mapping,args.gain_scale,args.keep_original_music,args.player_script,args.combat_config)
        elif args.action=='verify': print('Verified',len(verify(args.payload)['files']),'payload files')
        elif args.action=='install': install(args.payload,args.game_dir,args.dry_run)
        elif args.action=='uninstall': uninstall(args.game_dir)
    except (ValueError,OSError,EOFError,wave.Error,subprocess.SubprocessError) as e:
        parser.exit(1,'Error: '+str(e)+'\n')

if __name__=='__main__': main()
