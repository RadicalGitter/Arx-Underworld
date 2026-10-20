"""Retarget installed exploration music to an already installed arrangement.

No audio is distributed, no scripts are changed, and the original uninstall
backups remain authoritative. Save and close Arx before apply or recover.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import amb
import router_update
import routing
import score


def _entries(state):
    entries = {e['path']: e for e in state['entries']}
    if len(entries) != len(state['entries']):
        raise ValueError('Duplicate installation journal paths')
    return entries


def _check_asset(game, entries, path, digest):
    if path not in entries or entries[path]['installed'] != digest:
        raise ValueError('Replacement arrangement is not in the installation journal')
    data = score.safe_path(game, path).read_bytes()
    if score.sha(data) != digest:
        raise ValueError('Replacement arrangement changed: ' + path)
    score.wav_info(data)


def prepare(game, source, replacement, stage, mapping=score.ROOT/'mapping.csv'):
    game, stage = Path(game), Path(stage)
    if source == replacement or not all(re.fullmatch(r'uw[12]_\d{2}', t) for t in (source, replacement)):
        raise ValueError('Use two different soundtrack IDs')
    state = json.loads(score.state_path(game).read_text())
    if state['status'] != 'installed' or state.get('pending_music_update') or state.get('pending_router_update'):
        raise ValueError('Installation needs recovery first')
    entries = _entries(state)
    table = score.rows(mapping)
    if any(r['track'] == source for r in table):
        raise ValueError('Replace every source-track assignment in mapping.csv first')
    managed = [r for r in table if r['enabled'] == '1' and r['ambiance'] != 'ambient_menu']
    cues = {routing.music_name(i): r for i, r in enumerate(managed, 1)}
    updates, assets = [], {}
    for path, entry in entries.items():
        if not path.startswith('sfx/ambiance/') or not path.endswith('.amb'):
            continue
        before = score.safe_path(game, path).read_bytes()
        if score.sha(before) != entry['installed']:
            raise ValueError('Installed ambience changed: ' + path)
        parsed = amb.parse(before)
        tracks, changed = [], False
        for track in parsed.tracks:
            match = re.fullmatch(r'sfx/uwscore/' + re.escape(source) + r'_([0-9a-f]{8})\.wav', track.path)
            if not match:
                tracks.append(track)
                continue
            cue = cues.get(Path(path).stem)
            if not cue or cue['role'] != 'exploration' or cue['track'] != replacement:
                raise ValueError('Focused update requires an exploration cue with matching new mapping')
            target = 'sfx/uwscore/' + replacement + '_' + match[1] + '.wav'
            if target not in entries:
                raise ValueError('Build/install the replacement arrangement first: ' + target)
            assets[target] = entries[target]['installed']
            _check_asset(game, entries, target, assets[target])
            tracks.append(track.with_path(target))
            changed = True
        if changed:
            after = amb.Ambiance(parsed.version, tracks).encode()
            updates.append({'path': path, 'before': entry['installed'], 'after': score.sha(after), 'data': after})
    if not updates:
        raise ValueError('No installed references to the source track')
    if stage.exists():
        raise ValueError('Use a new staging directory')
    stage.mkdir(parents=True)
    for update in updates:
        score.atomic(score.safe_path(stage, update['path']), update.pop('data'))
    record = {'kind': 'private-music-update', 'source': source, 'replacement': replacement,
              'updates': updates, 'assets': assets}
    score.save_json(stage/'music-update.json', record)
    return record


def recover(game):
    state = json.loads(score.state_path(game).read_text())
    pending = state.get('pending_music_update')
    if pending:
        entries = _entries(state)
        for update in pending:
            path = update['path']
            if path not in entries or not path.startswith('sfx/ambiance/') or not path.endswith('.amb'):
                raise ValueError('Invalid pending music update')
            current = score.sha(score.safe_path(game, path).read_bytes())
            if current not in (update['before'], update['after']):
                raise ValueError('Ambience changed during interrupted update: ' + path)
            entries[path]['installed'] = current
        state.pop('pending_music_update')
        state['status'] = 'installed'
        score.save_json(score.state_path(game), state)
    return state


def apply(game, stage):
    router_update.require_closed()
    game, stage = Path(game), Path(stage)
    record = json.loads((stage/'music-update.json').read_text())
    if record.get('kind') != 'private-music-update' or not record['updates']:
        raise ValueError('Wrong music update format')
    state = recover(game)
    if state['status'] != 'installed' or state.get('pending_router_update'):
        raise ValueError('Installation needs recovery first')
    entries, seen, pending = _entries(state), set(), []
    for asset, digest in record['assets'].items():
        _check_asset(game, entries, asset, digest)
    for update in record['updates']:
        path = update['path']
        if path in seen or path not in entries or not path.startswith('sfx/ambiance/') or not path.endswith('.amb'):
            raise ValueError('Invalid music update path')
        seen.add(path)
        data = score.safe_path(stage, path).read_bytes()
        if score.sha(data) != update['after']:
            raise ValueError('Staged ambience checksum failed')
        parsed = amb.parse(data)
        if any(t.path.startswith('sfx/uwscore/') and t.path not in entries for t in parsed.tracks):
            raise ValueError('Uninstalled music sample')
        before = score.safe_path(game, path).read_bytes()
        current = score.sha(before)
        if current != entries[path]['installed'] or current not in (update['before'], update['after']):
            raise ValueError('Ambience changed since preparation: ' + path)
        if current != update['after']:
            pending.append((update, before, data))
    if not pending:
        return 'already applied'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    backup = game/'.uwscore-state/music-updates'/stamp
    score.atomic(backup/'state.json', score.state_path(game).read_bytes())
    for update, before, _ in pending:
        score.atomic(score.safe_path(backup, update['path']), before)
    state['status'] = 'updating-music'
    state['pending_music_update'] = [u for u, _, _ in pending]
    score.save_json(score.state_path(game), state)
    for update, before, data in pending:
        dest = score.safe_path(game, update['path'])
        if dest.read_bytes() != before:
            raise ValueError('Ambience changed during update: ' + update['path'])
        score.atomic(dest, data)
    recover(game)
    return 'applied'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--game-dir', required=True, type=Path)
    p.add_argument('--source', required=True)
    p.add_argument('--replacement', required=True)
    p.add_argument('--stage', required=True, type=Path)
    p = sub.add_parser('apply')
    p.add_argument('--game-dir', required=True, type=Path)
    p.add_argument('--stage', required=True, type=Path)
    p = sub.add_parser('recover')
    p.add_argument('--game-dir', required=True, type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print('Prepared', len(prepare(args.game_dir, args.source, args.replacement, args.stage)['updates']), 'music cues')
    elif args.action == 'apply':
        print('Music update:', apply(args.game_dir, args.stage))
    else:
        router_update.require_closed()
        print('Music journal:', recover(args.game_dir)['status'])


if __name__ == '__main__':
    main()
