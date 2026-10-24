"""Check a built POP909-CL release against its sources and its own metadata.

    python scripts/validate_release.py \
        --quantized /path/to/POP09-PIANOROLL-24-bin-quantization.zip --release POP909_processed
"""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import zipfile

import mido
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['MELODY', 'BRIDGE', 'PIANO', 'CHORDS']


def events(track):
    tick = 0
    for message in track:
        tick += message.time
        yield tick, message


def onsets(track):
    return Counter((t, m.note) for t, m in events(track) if m.type == 'note_on' and m.velocity)


def check_piece(piece, path, arrays, annotated):
    midi = mido.MidiFile(path)
    assert [t.name for t in midi.tracks[1:]] == NAMES, 'track layout'
    shift = piece['total_shift_ticks']
    for track, name in zip(midi.tracks[1:4], ('melody', 'bridge', 'piano')):
        expected = Counter((int(round(s * 24)) * 20 + shift, int(p)) for s, e, p, v in arrays[name])
        assert onsets(track) == expected, f'{name} notes differ from the 24-bin score'
        for t, m in events(track):
            assert m.type != 'control_change' or m.control in (64, 66, 67), 'unexpected controller'
    # Chords: the raw annotation moved by (total shift - annotator shift), up to the 1/16-beat snap.
    raw = mido.MidiFile(annotated)
    note_tracks = [t for t in raw.tracks if any(m.type == 'note_on' and m.velocity for m in t)]
    delta = shift - piece['annotator_shift_ticks']
    def by_pitch(counter, offset=0):
        result = {}
        for (t, p), n in counter.items():
            result.setdefault(p, []).extend([t + offset] * n)
        return {p: sorted(ts) for p, ts in result.items()}
    source, written = by_pitch(onsets(note_tracks[-1]), delta), by_pitch(onsets(midi.tracks[4]))
    if not piece['chord_zero_length_notes_dropped']:
        assert source.keys() == written.keys() and all(
            len(source[p]) == len(written[p]) and all(abs(a - b) <= 30 for a, b in zip(source[p], written[p]))
            for p in source), 'chords differ from annotation'
    first = min(t for track in midi.tracks[1:] for t, m in events(track) if m.type == 'note_on' and m.velocity)
    bar = piece['beats_per_bar'] * 480
    assert 0 <= first < bar and first == piece['first_onset_tick'], 'first onset is not in bar 1'
    meta = [(t, m) for t, m in events(midi.tracks[0]) if m.is_meta]
    tempos = [m.tempo for t, m in meta if m.type == 'set_tempo']
    assert tempos == [600000 * midi.ticks_per_beat // 480] and midi.ticks_per_beat == piece['ppq'], 'tempo / PPQ'
    keys = [(t, m.key) for t, m in meta if m.type == 'key_signature']
    meters = [(t, f'{m.numerator}/{m.denominator}') for t, m in meta if m.type == 'time_signature']
    assert keys == [(c['tick'], c['key']) for c in piece['key_changes']], 'key events differ from metadata'
    assert meters == [(c['tick'], c['meter']) for c in piece['meter_changes']], 'meter events differ from metadata'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--quantized', type=Path, required=True)
    parser.add_argument('--release', type=Path, default=ROOT / 'POP909_processed')
    parser.add_argument('--annotated', type=Path, default=ROOT / 'POP909_chord_annotated')
    args = parser.parse_args()
    pieces = json.loads((args.release / 'metadata.json').read_text())['pieces']
    assert [p['piece_id'] for p in pieces] == [f'{i:03d}' for i in range(1, 910)], 'metadata must list 001-909'
    files = sorted(p.name for p in args.release.iterdir() if p.suffix == '.mid')
    released = [p for p in pieces if p['status'] == 'released']
    assert files == [f'{p["piece_id"]}.mid' for p in released], 'MIDI files and released pieces differ'
    failures = {}
    with zipfile.ZipFile(args.quantized) as archive:
        for piece in released:
            sid = piece['piece_id']
            arrays = np.load(io.BytesIO(archive.read(f'POP09-PIANOROLL-24-bin-quantization/{sid}.npz')), allow_pickle=True)
            try:
                check_piece(piece, args.release / f'{sid}.mid', arrays, args.annotated / f'{sid}.mid')
            except AssertionError as error:
                failures[sid] = str(error)
    print(json.dumps({'released': len(released), 'missing': [p['piece_id'] for p in pieces if p['status'] == 'missing'],
                      'flagged': sum(bool(p['flags']) for p in released), 'failures': failures}, indent=1))
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
