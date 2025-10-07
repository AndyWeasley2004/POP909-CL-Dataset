import argparse
import csv
from pathlib import Path
import shutil
from typing import List, Dict, Tuple, Set

import miditoolkit
from tqdm import tqdm

# (major, minor, diminished, augmented, sus2, sus4)
TRIAD_NAMES = ["M", "m", "o", "+", "sus2", "sus4"]
TRIAD_DEGREES = [
    {0, 4, 7},
    {0, 3, 7},
    {0, 3, 6},
    {0, 4, 8},
    {0, 2, 7},
    {0, 5, 7},
]

# (dominant 7th, major 7th, minor 7th, half-diminished 7th, diminished 7th, minor-major 7th, augmented 7th)
SEVENTH_NAMES = ["D7", "M7", "m7", "/o7", "o7", "mM7", "+7"]
SEVENTH_DEGREES = [
    {0, 4, 7, 10},
    {0, 4, 7, 11},
    {0, 3, 7, 10},
    {0, 3, 6, 10},
    {0, 3, 6, 9},
    {0, 3, 7, 11},
    {0, 4, 8, 10},
]
PITCH_CLASS_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def get_chord_quality(pitch_classes: Set[int]) -> Tuple[int, str]:
    if not pitch_classes:
        return -1, "N"

    pcs = sorted(list(pitch_classes))
    for root_pc in pcs:
        degrees = {(pc - root_pc) % 12 for pc in pcs}

        for i, seventh_degrees in enumerate(SEVENTH_DEGREES):
            if degrees == seventh_degrees:
                return root_pc, SEVENTH_NAMES[i]

        for i, triad_degrees in enumerate(TRIAD_DEGREES):
            if degrees == triad_degrees:
                return root_pc, TRIAD_NAMES[i]

    return -1, "other"

def process_pop909(
    pop909_root: Path,
    out_root: Path,
):
    """Process the POP909 dataset and export pieces into *out_root*."""
    midi_paths = list(pop909_root.glob("*.mid"))
    
    for midi_path in tqdm(midi_paths, desc="POP909 -> gross dataset"):
        piece_name = midi_path.stem
        piece_out_dir = out_root / piece_name
        piece_out_dir.mkdir(parents=True, exist_ok=True)

        midi_file = miditoolkit.MidiFile(midi_path)
        if not midi_file.instruments or not midi_file.instruments[0].notes:
            print(f"Skipping {piece_name}: no score track or notes found.")
            continue

        score_track = midi_file.instruments[0]
        time_shift = min(note.start for note in score_track.notes)

        if time_shift > 0:
            for instrument in midi_file.instruments:
                for note in instrument.notes:
                    note.start -= time_shift
                    note.end -= time_shift
        
        # Save shifted score
        score_only_midi = miditoolkit.MidiFile()
        score_only_midi.instruments.append(score_track)
        score_only_midi.dump(piece_out_dir / f"{piece_name}.mid")

        # Process chord annotations
        chord_track = midi_file.instruments[-1]
        
        notes_by_time: Dict[int, List[miditoolkit.Note]] = {}
        for note in chord_track.notes:
            if note.start not in notes_by_time:
                notes_by_time[note.start] = []
            notes_by_time[note.start].append(note)
        
        key_signatures = midi_file.key_signature_changes
        chord_blocks = []
        for start_time, notes in sorted(notes_by_time.items()):
            if not notes:
                continue

            end_time = max(n.end for n in notes)
            pitch_classes = {note.pitch % 12 for note in notes}
            bass_pc = min(notes, key=lambda n: n.pitch).pitch % 12
            root_pc, quality = get_chord_quality(pitch_classes)

            current_key_str = "C"
            if key_signatures:
                active_ks = None
                for ks in key_signatures:
                    if ks.time <= start_time:
                        active_ks = ks
                    else:
                        break
                if active_ks:
                    key_name = active_ks.key_name
                    if " " in key_name:
                        key_root, mode, *_ = key_name.split()
                        if mode == "major":
                            current_key_str = key_root
                        else:
                            current_key_str = key_root.lower()
                    elif key_name.endswith('m'):
                        current_key_str = key_name[:-1].lower()
                    else:
                        current_key_str = key_name

            if root_pc != -1:
                chord_blocks.append({
                    "start": start_time,
                    "end": end_time,
                    "root": PITCH_CLASS_NAMES[root_pc],
                    "quality": quality,
                    "bass": PITCH_CLASS_NAMES[bass_pc],
                    "local_key": current_key_str,
                })

        all_events = []
        ticks_per_beat = midi_file.ticks_per_beat

        # Gap at beginning
        if not chord_blocks or chord_blocks[0]['start'] > 0:
            all_events.append({'time': 0.0, 'is_n': True})
        
        for i, block in enumerate(chord_blocks):
            # Real chord
            all_events.append({
                'time': block['start'] / ticks_per_beat,
                'is_n': False,
                'root': block['root'],
                'quality': block['quality'],
                'bass': block['bass'],
                'local_key': block['local_key']
            })

            # Gap after?
            end_qb = block['end'] / ticks_per_beat
            is_last = i == len(chord_blocks) - 1
            if not is_last:
                next_start_qb = chord_blocks[i+1]['start'] / ticks_per_beat
                if next_start_qb > end_qb:
                    all_events.append({'time': end_qb, 'is_n': True})
        
        all_events.sort(key=lambda x: x['time'])

        final_chord_events = []
        last_time = -1.0
        for event in all_events:
            if abs(event['time'] - last_time) < 1e-6:
                if not event['is_n'] and final_chord_events and final_chord_events[-1][1] == 'N':
                    final_chord_events[-1] = [f"{event['time']:.4f}", event['root'], event['quality'], event['bass'], event['local_key']]
                continue

            if event['is_n']:
                final_chord_events.append([f"{event['time']:.4f}", 'N', 'N', 'N', 'N'])
            else:
                final_chord_events.append([f"{event['time']:.4f}", event['root'], event['quality'], event['bass'], event['local_key']])
            
            last_time = event['time']

        # Write chord events to CSV
        with open(piece_out_dir / "chord_symbol.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["offset_qb", "root", "quality", "bass", "local_key"])
            writer.writerows(final_chord_events)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build the stage-1 gross dataset from POP909.")
    p.add_argument(
        "--pop909-root", type=Path, default=Path("POP909_processed")
    )
    p.add_argument("--out", type=Path, default=Path("data_root/all_data_collection"))
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    process_pop909(args.pop909_root, args.out)

    print("\nSUMMARY")
    print(f"POP909 processing complete. Output at {args.out}")