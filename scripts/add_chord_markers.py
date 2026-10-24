"""Write chord labels into each MIDI file as timed marker events on track 0.

Each chord in the CHORDS track gets a marker such as "C#:m7" (or "C#:m7/E" when
the bass is not the root) at its onset. Labels come from the same template
matching as process_pop909.py; pitch sets matching no template get no marker.
Existing markers are replaced, so the script can be re-run.

    python scripts/add_chord_markers.py --midi-dir POP909_processed
"""
import argparse
from pathlib import Path
import sys

import mido

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from process_pop909 import get_chord_quality, PITCH_CLASS_NAMES


def chord_markers(chord_track):
    """(tick, label) for each chord onset; chord tones starting together form one chord."""
    onsets, tick = {}, 0
    for message in chord_track:
        tick += message.time
        if message.type == 'note_on' and message.velocity:
            onsets.setdefault(tick, []).append(message.note)
    markers = []
    for tick, pitches in sorted(onsets.items()):
        root, quality = get_chord_quality({p % 12 for p in pitches})
        if root == -1:
            continue
        label = f'{PITCH_CLASS_NAMES[root]}:{quality}'
        bass = min(pitches) % 12
        if bass != root:
            label += f'/{PITCH_CLASS_NAMES[bass]}'
        markers.append((tick, label))
    return markers


def add_markers(path):
    midi = mido.MidiFile(path)
    chords = [t for t in midi.tracks if t.name == 'CHORDS']
    if len(chords) != 1:
        raise ValueError(f'{path.name}: expected one CHORDS track')
    events, tick = [], 0
    for order, message in enumerate(midi.tracks[0]):
        tick += message.time
        if message.type not in ('marker', 'end_of_track'):
            events.append((tick, order, message))
    markers = chord_markers(chords[0])
    events += [(t, len(events) + i, mido.MetaMessage('marker', text=label, time=0)) for i, (t, label) in enumerate(markers)]
    track, previous = mido.MidiTrack(), 0
    for tick, _, message in sorted(events, key=lambda e: (e[0], e[1])):
        track.append(message.copy(time=tick - previous))
        previous = tick
    track.append(mido.MetaMessage('end_of_track', time=0))
    midi.tracks[0] = track
    midi.save(path)
    return len(markers)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--midi-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'POP909_processed')
    args = parser.parse_args()
    total = sum(add_markers(path) for path in sorted(args.midi_dir.glob('*.mid')))
    print(f'Wrote {total} chord markers')


if __name__ == '__main__':
    main()
