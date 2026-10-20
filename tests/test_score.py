import array,csv,io,json,pathlib,struct,sys,tempfile,unittest,wave
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import amb,score

def fixture(version=0x01000003):
    # Separate environment track plus short master bed, each with arbitrary keys.
    a=amb.music_track(version,'sfx/rat.wav',.8)
    b=amb.music_track(version,'sfx/ambiance/music.wav',.6)
    tail=bytearray(b.tail);struct.pack_into('<I',tail,1 if version>=0x01000002 else 0,4)
    return amb.Ambiance(version,[a,amb.Track(b.path_bytes,bytes(tail))]).encode()

class AmbTests(unittest.TestCase):
    def test_roundtrip_and_preservation(self):
        for version in amb.VERSIONS:
            data=fixture(version);a=amb.parse(data);self.assertEqual(a.encode(),data)
            new=amb.parse(amb.patch(data,'sfx/uwscore/new.wav',.3,{'sfx/ambiance/music.wav':'sfx/uwscore/anchor.wav'}))
            self.assertEqual(new.tracks[0].encode(),a.tracks[0].encode())
            self.assertEqual(new.tracks[1].tail,a.tracks[1].tail)
            self.assertEqual(new.tracks[1].header(version)[0],4)
            self.assertEqual(new.tracks[-1].header(version)[0],0)
            self.assertEqual(new.tracks[-1].header(version)[1],1)
    def test_malformed(self):
        for data in (b'',b'GAMB',fixture()[:-2],fixture()+b'x'):
            with self.assertRaises((ValueError,struct.error)): amb.parse(data)

class AudioTests(unittest.TestCase):
    def test_music_boost_and_peak_limiter(self):
        import math,shutil
        quiet=score.encode_wav(22050,array.array('h',[1000,-1000]*2205).tobytes())
        boost=20*math.log10(2)
        _,frames,pcm=score.wav_info(score.boost_music(quiet,boost))
        values=array.array('h');values.frombytes(pcm)
        self.assertEqual(frames,4410);self.assertEqual(max(values),2000)
        for invalid in (-1,19,float('nan')):
            with self.assertRaises(ValueError):score.boost_music(quiet,invalid)
        if not shutil.which('ffmpeg'):self.skipTest('Peak limiting needs FFmpeg')
        rate=22050
        loud=score.encode_wav(rate,array.array('h',(round(24000*math.sin(i*.17)) for i in range(rate))).tobytes())
        _,frames,pcm=score.wav_info(score.boost_music(loud,boost))
        values=array.array('h');values.frombytes(pcm)
        self.assertEqual(frames,rate)
        self.assertLessEqual(max(abs(v) for v in values),math.ceil(32768*10**(-1/20)))
        self.assertGreater(max(values),24000)
    def test_gain_matches_engine_logarithmic_curve(self):
        # Values are amplitude targets, not Arx's 0-1 logarithmic controls.
        for desired in (.19,.2,.32,.42,.5,.65,.9,1.0):
            native=score.arx_volume_control(desired)
            self.assertAlmostEqual(100000.0**native/100000.0,desired,places=7)
        self.assertAlmostEqual(score.arx_volume_control(.5),.9397940008672038)
        self.assertEqual(score.arx_volume_control(0),0)
        for invalid in (-1,1.01,float('nan'),float('inf')):
            with self.assertRaises(ValueError):score.arx_volume_control(invalid)
    def test_arrangement_clips_fades_and_adds_silence(self):
        rate,frames,pcm=score.wav_info(score.arrange(score.encode_wav(100,b'\x00\x20'*500),2,3))
        self.assertEqual((rate,frames),(100,500))
        self.assertEqual(pcm[398:],b'\0'*602)
    def test_adpcm_fact_clamps_anchor_duration(self):
        # Two 256-byte blocks can decode 1000 frames, but fact specifies 997.
        fmt=struct.pack('<HHIIHHHH',2,1,22050,11289,256,4,2,500)
        body=b'fmt '+struct.pack('<I',len(fmt))+fmt+b'fact'+struct.pack('<II',4,997)+b'data'+struct.pack('<I',512)+b'\0'*512
        data=b'RIFF'+struct.pack('<I',len(body)+4)+b'WAVE'+body
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t)/'orig.wav';p.write_bytes(data)
            rate,frames,pcm=score.wav_info(score.silence_like(p))
            self.assertEqual((rate,frames),(22050,997));self.assertFalse(any(pcm))
    def test_normalization_and_fades(self):
        pcm=array.array('h',[10000,-10000]*22050)
        rate,frames,data=score.wav_info(score.normalize(score.encode_wav(22050,pcm.tobytes())))
        samples=array.array('h');samples.frombytes(data)
        self.assertEqual((rate,frames),(22050,44100))
        self.assertEqual(samples[0],0);self.assertEqual(samples[-1],0)
        self.assertLessEqual(max(abs(x) for x in samples),round(32767*10**(-3/20)))
    def test_encoded_audio_import(self):
        # Exercise actual conversion if FFmpeg is installed.
        import shutil,subprocess
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg not available')
        with tempfile.TemporaryDirectory() as t:
            p=pathlib.Path(t);(p/'raw.wav').write_bytes(score.encode_wav(22050,array.array('h',[1500,-1500]*11025).tobytes()))
            subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(p/'raw.wav'),str(p/'clip.flac')],check=True)
            score.import_audio(p/'clip.flac',p/'imported.wav')
            rate,frames,_=score.wav_info((p/'imported.wav').read_bytes());self.assertEqual((rate,frames),(22050,22050))

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.payload=self.root/'payload';self.game=self.root/'game';self.game.mkdir()
        self.relative='sfx/ambiance/ambient_test.amb'
        self.dest=self.game/self.relative;self.dest.parent.mkdir(parents=True)
        self.dest.write_bytes(b'previous-mod')
        music=score.encode_wav(22050,b'\0'*440)
        sample='sfx/uwscore/new.wav'
        cue=amb.Ambiance(0x01000003,[amb.music_track(0x01000003,sample,.4)]).encode()
        (self.payload/self.relative).parent.mkdir(parents=True);(self.payload/self.relative).write_bytes(cue)
        (self.payload/sample).parent.mkdir(parents=True);(self.payload/sample).write_bytes(music)
        score.save_json(self.payload/'mod-manifest.json',{'kind':'arx-underworld-music','files':{self.relative:score.sha(cue),sample:score.sha(music)}})
    def tearDown(self):self.temp.cleanup()
    def test_dryrun_does_not_write(self):
        score.install(self.payload,self.game,True)
        self.assertEqual(self.dest.read_bytes(),b'previous-mod');self.assertFalse(score.state_path(self.game).exists())
    def test_install_uninstall_preserves_existing(self):
        score.install(self.payload,self.game)
        self.assertNotEqual(self.dest.read_bytes(),b'previous-mod')
        score.uninstall(self.game)
        self.assertEqual(self.dest.read_bytes(),b'previous-mod');self.assertFalse((self.game/'sfx/uwscore/new.wav').exists())
    def test_edit_conflict_is_atomic(self):
        score.install(self.payload,self.game);self.dest.write_bytes(b'edited')
        with self.assertRaises(ValueError):score.uninstall(self.game)
        self.assertEqual(self.dest.read_bytes(),b'edited');self.assertTrue((self.game/'sfx/uwscore/new.wav').exists())
    def test_reinstall_rejected(self):
        score.install(self.payload,self.game)
        with self.assertRaises(ValueError):score.install(self.payload,self.game)
    def test_payload_tamper_rejected(self):
        (self.payload/self.relative).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):score.install(self.payload,self.game)
        self.assertEqual(self.dest.read_bytes(),b'previous-mod')
    def test_interrupted_install_recovery(self):
        original=score.atomic;writes=0
        def failing(path,data):
            nonlocal writes
            if str(path).startswith(str(self.game/'sfx')):
                writes+=1
                if writes==2:raise OSError('simulated interruption')
            return original(path,data)
        with patch.object(score,'atomic',failing):
            with self.assertRaises(OSError):score.install(self.payload,self.game)
        self.assertEqual(json.loads(score.state_path(self.game).read_text())['status'],'installing')
        score.uninstall(self.game);self.assertEqual(self.dest.read_bytes(),b'previous-mod')
    def test_paths_and_links_rejected(self):
        for path in ('../x','/x','sfx/../x','sfx/x:stream','sfx\\x'):
            with self.assertRaises(ValueError):score.safe_path(self.game,path)
        try:(self.game/'linked').symlink_to(self.payload,target_is_directory=True)
        except OSError:return
        with self.assertRaises(ValueError):score.safe_path(self.game,'linked/test.wav')

if __name__=='__main__':unittest.main()


class NormalisationTests(unittest.TestCase):
    def test_music_cut_is_exact_scaling_without_limiter(self):
        import math
        tone=score.encode_wav(22050,array.array('h',[8000,-8000]*100).tobytes())
        _,frames,pcm=score.wav_info(score.gain_music(tone,20*math.log10(0.5)))
        v=array.array('h');v.frombytes(pcm)
        self.assertEqual(frames,200);self.assertEqual(max(v),4000)
        with self.assertRaises(ValueError):score.gain_music(tone,-41)
    def test_environment_volume_shift_is_logarithmic_and_volume_only(self):
        import struct
        track=amb.music_track(0x01000003,'sfx/ambiance/wind.wav',0.9)
        shifted=amb.scale_volume(track,0x01000003,-6)
        base=amb._key_base(track,0x01000003)+8+amb.VOLUME_OFFSET
        self.assertAlmostEqual(struct.unpack_from('<f',shifted.tail,base)[0],0.84,places=5)
        self.assertEqual(amb.without_volumes(track,0x01000003),amb.without_volumes(shifted,0x01000003))
        silent=amb.music_track(0x01000003,'sfx/ambiance/x.wav',0.0)
        self.assertEqual(struct.unpack_from('<f',amb.scale_volume(silent,0x01000003,-6).tail,base)[0],0.0)
    def test_normalisation_gain_targets_and_guards(self):
        self.assertEqual(score.normalisation_gain(-20,-30.5),10.5)
        self.assertEqual(score.normalisation_gain(-20,-70),0.0)
        self.assertEqual(score.normalisation_gain(-20,-45),18.0)
    def test_mix_settings_and_uniform_cue_gains(self):
        mix=score.load_mix()
        self.assertEqual(mix['target'],-20.0);self.assertEqual(mix['environment_db'],-6.0)
        gains={r['gain'] for r in csv.DictReader((score.ROOT/'mapping.csv').open(encoding='utf-8'))}
        self.assertEqual(gains,{'0.9'})
    def test_router_plays_every_music_layer_at_one_volume(self):
        import re,routing
        text=open(score.ROOT/'routing.py',encoding='utf-8').read()
        self.assertNotIn('AMBIANCE -v @uwsc_volume',text)
        self.assertEqual(routing.MUSIC_VOLUME,100)
