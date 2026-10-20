"""Build a shareable kit. Owner game data and private music are never selected."""
import argparse,csv,hashlib,pathlib,zipfile,json
ROOT=pathlib.Path(__file__).resolve().parent
FILES=['README.md','RELEASE-REPORT.md','LICENSE.txt','AGENTS.md','.gitignore','score.py','amb.py','combat.py','routing.py','combat.json','mix.json','package.py','mapping.csv','tracks.csv','import.csv','Install-Test-Mod.cmd','Install-Underworld-Mod.cmd','Uninstall-Mod.cmd']
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=pathlib.Path);a=p.parse_args()
    chosen=[ROOT/n for n in FILES]
    chosen+=sorted((ROOT/'docs').glob('*.md'))+sorted((ROOT/'docs').glob('*.json'))+sorted((ROOT/'tests').glob('*.py'))
    tracks={r['track'] for r in csv.DictReader((ROOT/'mapping.csv').open(encoding='utf-8'))}
    chosen+=[ROOT/'placeholders'/(t+'.wav') for t in sorted(tracks)]
    # Never include .work, assets, builds, archive extractions, synths or ROMs.
    # Placeholder bytes must match a known source-generated allowlist.
    expected=json.loads((ROOT/'placeholders/checksums.json').read_text())
    for f in chosen:
        if f.parent==ROOT/'placeholders' and hashlib.sha256(f.read_bytes()).hexdigest()!=expected[f.name]:raise ValueError('Placeholder changed: '+str(f))
    chosen.append(ROOT/'placeholders/checksums.json')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in chosen:
            name='ArxUnderworldMusic-0.2.0/'+f.relative_to(ROOT).as_posix()
            z.write(f,name)
    print(a.output, a.output.stat().st_size,'bytes;',len(chosen),'files')
if __name__=='__main__':main()
