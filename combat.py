"""Player-only adaptive music appendix. Never rewrites existing script bytes."""
import math
import re

PLAYER_SCRIPT = 'graph/obj3d/interactive/player/player.asl'
NORMAL = 'ambient_uwscore_combat_normal'
LOW = 'ambient_uwscore_combat_low'
MARKER = b'// UWSCORE PLAYER HEALTH CONTROLLER v1'


def validate(config):
    if type(config.get('enabled')) is not bool:
        raise ValueError('combat.enabled must be true or false')
    low = config.get('low_health_fraction')
    recover = config.get('recovery_health_fraction')
    if (type(low) not in (int, float) or type(recover) not in (int, float)
            or not math.isfinite(low) or not math.isfinite(recover)
            or not 0 < low < recover <= 1):
        raise ValueError('Require 0 < low health < recovery health <= 1')
    return config


def append_controller(original, config):
    validate(config)
    if not config['enabled']:
        return original
    # Arx scripts use single-byte local variable sigils, not UTF-8.
    text = original.decode('latin1')
    code = re.sub(r'//[^\r\n]*|/\*.*?\*/', '', text, flags=re.S)
    if '\0' in text or 'uwscore' in text.lower():
        raise ValueError('Player script already patched or contains embedded NUL')
    if re.search(r'\bon\s+main\b|\bsetmainevent\b|\bsetevent\s+main\b', code, re.I):
        raise ValueError('Player MAIN event is customized; refusing to replace it')
    for required in ('on ouch', '§fighting_amb', 'ambient_fight', 'ambiance_fight_end', 'ambiance_down'):
        if required not in code.lower():
            raise ValueError('Unsupported player combat script: missing ' + required)
    low = format(config['low_health_fraction'], '.8g')
    recover = format(config['recovery_health_fraction'], '.8g')
    # No new timers: original save-file byte offsets remain unchanged, and
    # removing the appendix cannot leave a timer pointing beyond the old EOF.
    appendix = f'''
{MARKER.decode()}
// ON MAIN is the engine heartbeat. Only player health and the native latch.
ON MAIN {{
 IF (§fighting_amb != 1) GOTO UWSCORE_STOP
 IF (^player_life <= 0) GOTO UWSCORE_STOP
 IF (^player_maxlife <= 0) GOTO UWSCORE_STOP
 SET @uwscore_threshold ^player_maxlife
 IF (§uwscore_state == 2) GOTO UWSCORE_RECOVERY_THRESHOLD
 MUL @uwscore_threshold {low}
 GOTO UWSCORE_SELECT
}}
>>UWSCORE_RECOVERY_THRESHOLD
 MUL @uwscore_threshold {recover}
>>UWSCORE_SELECT
 IF (§uwscore_state == 2) {{
  IF (^player_life >= @uwscore_threshold) GOTO UWSCORE_NORMAL
  GOTO UWSCORE_LOW
 }}
 IF (^player_life > @uwscore_threshold) GOTO UWSCORE_NORMAL
 GOTO UWSCORE_LOW
>>UWSCORE_NORMAL
 AMBIANCE -v 0 {LOW}
 AMBIANCE -v 90 {NORMAL}
 SET §uwscore_state 1
 ACCEPT
>>UWSCORE_LOW
 AMBIANCE -v 0 {NORMAL}
 AMBIANCE -v 90 {LOW}
 SET §uwscore_state 2
 ACCEPT
>>UWSCORE_STOP
 AMBIANCE -v 0 {NORMAL}
 AMBIANCE -v 0 {LOW}
 SET §uwscore_state 0
 ACCEPT
// END UWSCORE PLAYER HEALTH CONTROLLER
'''
    return original + appendix.replace('\n', '\r\n').encode('latin1')
