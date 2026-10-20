"""Strict GAMB parser/writer. Independently implemented from the published format.

Original track records survive byte-for-byte, except explicitly selected music
paths and the owner-requested uniform environmental volume shift. Both 1.0.0.2 and 1.0.0.3 are handled without reordering their key records.
"""
from dataclasses import dataclass
import struct

VERSIONS = (0x01000001, 0x01000002, 0x01000003)
KEY_SIZE = 116
MASTER = 4

@dataclass
class Track:
    path_bytes: bytes
    tail: bytes

    @property
    def path(self):
        return self.path_bytes.decode('latin1').replace('\\', '/').lower()

    def encode(self):
        return self.path_bytes + b'\0' + self.tail

    def header(self, version):
        offset = self.tail.index(b'\0') + 1 if version >= 0x01000002 else 0
        return struct.unpack_from('<II', self.tail, offset)

    def with_path(self, path):
        return Track(path.encode('ascii'), self.tail)

@dataclass
class Ambiance:
    version: int
    tracks: list

    def encode(self):
        return b'GAMB' + struct.pack('<II', self.version, len(self.tracks)) + b''.join(t.encode() for t in self.tracks)

def parse(data):
    if len(data) < 12 or data[:4] != b'GAMB':
        raise ValueError('Not a GAMB ambience')
    version, count = struct.unpack_from('<II', data, 4)
    if version not in VERSIONS or not 1 <= count <= 1024:
        raise ValueError('Unsupported GAMB version or track count')
    pos = 12
    tracks = []
    for _ in range(count):
        end = data.index(b'\0', pos)
        path = data[pos:end]
        if not path or len(path) > 4096:
            raise ValueError('Invalid sample path')
        pos = end + 1
        tail_start = pos
        if version >= 0x01000002:
            end = data.index(b'\0', pos)
            if end != pos:
                raise ValueError('Non-empty track name unsupported by engine')
            pos = end + 1
        flags, keys = struct.unpack_from('<II', data, pos)
        if not 1 <= keys <= 100000:
            raise ValueError('Invalid key count')
        pos += 8 + keys * KEY_SIZE
        if pos > len(data):
            raise ValueError('Truncated GAMB track')
        tracks.append(Track(path, data[tail_start:pos]))
    if pos != len(data):
        raise ValueError('Trailing GAMB data')
    return Ambiance(version, tracks)

VOLUME_OFFSET = 20   # within a 116-byte key: five u32 fields, then the volume setting (min f32, max f32, ...)

def _key_base(track, version):
    return track.tail.index(b'\0') + 1 if version >= 0x01000002 else 0

def scale_volume(track, version, decibels):
    """Return a copy of track with every key's volume min/max shifted by `decibels`.
    Arx's volume control is logarithmic: control = 1 + log10(amplitude) / 5, so a gain of
    d dB adds d/100 to the control. Silent keys stay silent; results clamp to [0.001, 1]."""
    tail = bytearray(track.tail); base = _key_base(track, version)
    flags, keys = struct.unpack_from('<II', tail, base)
    for k in range(keys):
        off = base + 8 + k * KEY_SIZE + VOLUME_OFFSET
        vmin, vmax = struct.unpack_from('<ff', tail, off)
        def shift(v): return 0.0 if v <= 0 else min(1.0, max(0.001, v + decibels / 100.0))
        struct.pack_into('<ff', tail, off, shift(vmin), shift(vmax))
    return Track(track.path_bytes, bytes(tail))

def without_volumes(track, version):
    """Track bytes with key volumes zeroed: used to prove only volumes changed."""
    tail = bytearray(track.tail); base = _key_base(track, version)
    flags, keys = struct.unpack_from('<II', tail, base)
    for k in range(keys):
        struct.pack_into('<ff', tail, base + 8 + k * KEY_SIZE + VOLUME_OFFSET, 0.0, 0.0)
    return track.path_bytes + b'\0' + bytes(tail)

def music_track(version, path, gain, delay_ms=0):
    # Non-master, fixed centre/pitch, 65,536 repeats. Native master keeps its
    # original cadence; this stream continues across its resets. No engine patch.
    key = struct.pack('<IIIII', 0, delay_ms, 65535, 0, 0)
    for value in (gain, 1.0, 0.0, 0.0, 0.0, 0.0):
        key += struct.pack('<ffII', value, value, 0, 0)
    tail = (b'\0' if version >= 0x01000002 else b'') + struct.pack('<II', 0, 1) + key
    return Track(path.encode('ascii'), tail)

def patch(data, cue, gain, anchors, environment_db=0.0):
    original = parse(data)
    # anchors maps selected original sample paths to equal-duration silence;
    # every other (environmental) track keeps its bytes except a uniform volume shift.
    changed = [t.with_path(anchors[t.path]) if t.path in anchors
               else scale_volume(t, original.version, environment_db) for t in original.tracks]
    changed.append(music_track(original.version, cue, gain))
    return Ambiance(original.version, changed).encode()
