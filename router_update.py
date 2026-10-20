"""Prepare/apply a private player-controller update without rebuilding audio.

Installed before-images and the ordinary uninstall journal remain authoritative.
No game process is launched or stopped. Private stages contain game script bytes.
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import combat
import routing
import score


def recover(game):
    path=score.state_path(game); state=json.loads(path.read_text())
    pending=state.get('pending_router_update')
    if pending:
        entry=next(e for e in state['entries'] if e['path']==combat.PLAYER_SCRIPT)
        current=score.sha(score.safe_path(game,combat.PLAYER_SCRIPT).read_bytes())
        if current not in (pending['before'],pending['after']):
            raise ValueError('Player changed during interrupted router update')
        entry['installed']=current
        if current==pending['after']:state['router_patch']=pending['patch']
        state.pop('pending_router_update');state['status']='installed'
        score.save_json(path,state)
    return state


def prepare(game,manifest_path,output):
    game=Path(game).resolve(); output=Path(output).resolve()
    state=json.loads(score.state_path(game).read_text())
    if state['status']!='installed' or state.get('pending_router_update'):
        raise ValueError('Installation needs recovery before preparing another update')
    entry=next(e for e in state['entries'] if e['path']==combat.PLAYER_SCRIPT)
    manifest=json.loads(Path(manifest_path).read_text())
    before=score.safe_path(game,combat.PLAYER_SCRIPT).read_bytes()
    digest=score.sha(before)
    if digest!=entry['installed'] or digest!=manifest['files'][combat.PLAYER_SCRIPT]:
        raise ValueError('Installed player must match both journal and source manifest')
    before_info=manifest['script_patches'][combat.PLAYER_SCRIPT]
    baseline=routing.verify_script(before,before_info)
    plan=manifest['music_router']; config=json.loads((score.ROOT/'combat.json').read_text())
    extra=routing.controller(baseline,config,plan['cues'],plan['zones'])
    after,after_info,_=routing.patch_script(baseline,plan['cues'],extra,bootstrap=True)
    if routing.verify_script(after,after_info)!=baseline:
        raise ValueError('Update changed original player script bytes')
    if output.exists():raise ValueError('Use a new staging directory')
    output.mkdir(parents=True)
    score.atomic(output/'player.asl',after)
    record={'kind':'private-router-update','before':digest,'after':score.sha(after),
            'before_patch':before_info,'patch':after_info,'settings':config,
            'source_manifest':str(Path(manifest_path).resolve())}
    score.save_json(output/'router-update.json',record)
    return record


def require_closed():
    if os.name=='nt':
        result=subprocess.run(['tasklist','/FI','IMAGENAME eq arx.exe','/FO','CSV','/NH'],
                              capture_output=True,text=True,check=True,timeout=15)
        if any(row and row[0].lower()=='arx.exe' for row in csv.reader(io.StringIO(result.stdout))):
            raise ValueError('Save and close Arx before applying the update')
        log=Path(os.environ['USERPROFILE'])/'Saved Games/Arx Libertatis/arx.log'
        if not log.is_file() or not log.read_text(errors='replace').rstrip().endswith('Clean shutdown'):
            raise ValueError('Arx log does not yet confirm Clean shutdown')


def apply(game,stage):
    require_closed()
    game=Path(game).resolve(); stage=Path(stage).resolve()
    record=json.loads((stage/'router-update.json').read_text())
    after=(stage/'player.asl').read_bytes()
    if record.get('kind')!='private-router-update' or score.sha(after)!=record['after']:
        raise ValueError('Staged update checksum failed')
    baseline=routing.verify_script(after,record['patch'])
    state=recover(game)
    if state['status']!='installed':raise ValueError('Installation is not ready for update')
    entry=next(e for e in state['entries'] if e['path']==combat.PLAYER_SCRIPT)
    dest=score.safe_path(game,combat.PLAYER_SCRIPT); before=dest.read_bytes()
    current=score.sha(before)
    if current==record['after'] and current==entry['installed']:return 'already applied'
    if current!=record['before'] or current!=entry['installed']:
        raise ValueError('Player changed since update was prepared; refusing to overwrite it')
    if routing.verify_script(before,record['before_patch'])!=baseline:
        raise ValueError('Update does not preserve the installed baseline')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    backup=score.safe_path(game,'.uwscore-state/router-updates/'+stamp+'/player.asl')
    score.atomic(backup,before)
    score.atomic(backup.parent/'state.json',score.state_path(game).read_bytes())
    state['status']='updating-router'
    state['pending_router_update']={k:record[k] for k in ('before','after','patch')}
    score.save_json(score.state_path(game),state)
    # Recheck after durable backups/journal, before the only game-script write.
    if score.sha(dest.read_bytes())!=current:raise ValueError('Player changed during update')
    score.atomic(dest,after)
    recover(game)
    if dest.read_bytes()!=after:raise ValueError('Installed player verification failed')
    return 'applied'


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--game-dir',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('apply');p.add_argument('--game-dir',type=Path,required=True);p.add_argument('--stage',type=Path,required=True)
    p=sub.add_parser('recover');p.add_argument('--game-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='prepare':
        r=prepare(args.game_dir,args.manifest,args.output)
        print('Prepared private controller update:',r['after'])
    elif args.action=='apply':print('Router update:',apply(args.game_dir,args.stage))
    else:
        require_closed();print('Router journal:',recover(args.game_dir)['status'])


if __name__=='__main__':main()
