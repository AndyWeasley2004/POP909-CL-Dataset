import os
import json
import shutil
import miditoolkit
from tqdm import tqdm
import re
import numpy as np

# --- Configuration ---
SRC_DIR = 'POP909_chord_annotated_cleaned'
DST_DIR = 'POP909_processed'
OPERATIONS_FILE = 'midi_operations.json'

# --- Helper Functions ---
SHARP_TO_FLAT = {
    'A#': 'Bb',
    'D#': 'Eb',
    'G#': 'Ab',
    'A#m': 'Bbm',
    'D#m': 'Ebm',
    'G#m': 'Abm',
    'Cbm': 'Bm',
    'C#': 'Db',
    'F#': 'Gb',
    'B#': 'C',
    'E#': 'F'
}

def time_to_ticks(midi_obj, time_str, unit):
    if unit == 'bar:beat':
        match = re.search(r'\d+', time_str)
        if not match:
            return 0
        bar = int(match.group(0))
        
        # Manually calculate ticks from bar number
        ticks_per_bar = 4 * midi_obj.ticks_per_beat 
        ts_changes = sorted(midi_obj.time_signature_changes, key=lambda x: x.time)

        current_tick = 0
        current_bar = 1
        last_ts_tick = 0
        # Use a default TS if none are in the file
        last_ts = ts_changes[0] if ts_changes else miditoolkit.TimeSignature(4, 4, 0)

        for ts in ts_changes:
            if ts.time == 0: continue # Skip initial TS if it is at tick 0, already accounted for
            
            bars_in_segment = (ts.time - last_ts_tick) / (last_ts.numerator * midi_obj.ticks_per_beat * 4 / last_ts.denominator)
            
            if current_bar + bars_in_segment >= bar:
                break
                
            current_tick = ts.time
            current_bar += bars_in_segment
            last_ts_tick = ts.time
            last_ts = ts

        ticks_per_bar_current = last_ts.numerator * midi_obj.ticks_per_beat * 4 / last_ts.denominator
        remaining_bars = bar - current_bar
        return int(current_tick + remaining_bars * ticks_per_bar_current)
        
    elif unit == 'minute:second:ms' or unit == 's':
        # Parse seconds robustly
        seconds: float
        if unit == 's':
            try:
                seconds = float(time_str)
            except Exception:
                return 0
        else:
            # Accept formats like MM:SS or MM:SS:ms (ms in 0..999)
            m = re.match(r"^\s*(\d+):(\d+)(?::(\d+))?\s*$", str(time_str))
            if not m:
                return 0
            minutes = int(m.group(1))
            secs = int(m.group(2))
            ms_part = m.group(3)
            millis = int(ms_part) if ms_part is not None else 0
            seconds = minutes * 60 + secs + (millis / 1000.0)

        # Convert seconds to ticks using miditoolkit's tempo-aware mapping
        try:
            tick_to_time = midi_obj.get_tick_to_time_mapping()
            # Locate nearest tick to requested time
            idx = int(np.searchsorted(tick_to_time, seconds, side='left'))
            if idx <= 0:
                return 0
            if idx >= len(tick_to_time):
                return int(midi_obj.max_tick)
            # Choose the closer between idx-1 and idx
            prev_diff = abs(seconds - tick_to_time[idx - 1])
            curr_diff = abs(seconds - tick_to_time[idx])
            return int(idx - 1 if prev_diff <= curr_diff else idx)
        except Exception:
            # Fallback to constant-tempo approximation using current (last) tempo
            # This is a conservative fallback; normally the mapping path should succeed
            bpm = midi_obj.tempo_changes[0].tempo if midi_obj.tempo_changes else 120
            seconds_per_tick = (60.0 / float(bpm)) / float(midi_obj.ticks_per_beat)
            return int(seconds / seconds_per_tick)

    return 0

# --- Operation Handlers ---

def handle_time_signature_change(midi_obj, op):
    try:
        numerator, denominator = map(int, op['time_signature'].split('/'))
        time_tick = 0
        
        if 'time' in op:
            time_tick = time_to_ticks(midi_obj, op['time'], 'minute:second:ms')
        
        # If it is a global change (at tick 0), remove existing ones
        if time_tick == 0:
            midi_obj.time_signature_changes = [ts for ts in midi_obj.time_signature_changes if ts.time != 0]

        midi_obj.time_signature_changes.append(
            miditoolkit.TimeSignature(numerator, denominator, int(time_tick))
        )
        # Keep sorted
        midi_obj.time_signature_changes.sort(key=lambda x: x.time)

    except Exception as e:
        print(f"Error handling time signature change for op {op}: {e}")


def handle_key_signature_change(midi_obj, op):
    try:
        time_tick = time_to_ticks(midi_obj, op['time'], op['unit'])
        key_name = op['key']
        if key_name in SHARP_TO_FLAT:
            key_name = SHARP_TO_FLAT[key_name]
        
        midi_obj.key_signature_changes.append(
            miditoolkit.KeySignature(key_name=key_name, time=int(time_tick))
        )
    except Exception as e:
        print(f"Error handling key signature change for op {op}: {e}")


def handle_start_beat_shift(midi_obj, op):
    try:
        # Determine if there are notes to shift
        has_notes = any(len(instr.notes) > 0 for instr in midi_obj.instruments)
        if not has_notes:
            return

        first_note_time = min([
            note.start
            for instrument in midi_obj.instruments
            for note in instrument.notes
        ])

        if 'to_beat' in op:
            target_beat = int(op['to_beat'])

            # Find the active time signature at the first note
            current_ts = miditoolkit.TimeSignature(4, 4, 0)
            for ts in sorted(midi_obj.time_signature_changes, key=lambda x: x.time):
                if ts.time <= first_note_time:
                    current_ts = ts
                else:
                    break

            # Compute ticks per bar and the TS-based beat unit in ticks (denominator-aware)
            ticks_per_bar = int(round(current_ts.numerator * midi_obj.ticks_per_beat * 4 / current_ts.denominator))
            unit_ticks = int(round(midi_obj.ticks_per_beat * 4 / current_ts.denominator))
            if ticks_per_bar <= 0 or unit_ticks <= 0:
                return

            # Clamp destination beat within the bar [1, numerator]
            if current_ts.numerator > 0:
                if target_beat < 1:
                    target_beat = 1
                elif target_beat > current_ts.numerator:
                    target_beat = current_ts.numerator

            # Compute tick position within current bar for the first note
            # Use integer arithmetic to avoid FP drift
            # Determine how many whole bars have elapsed since the current TS start
            last_ts_tick = current_ts.time
            ticks_since_ts = max(0, first_note_time - last_ts_tick)
            bars_since_ts = ticks_since_ts // ticks_per_bar
            bar_start_tick = last_ts_tick + bars_since_ts * ticks_per_bar
            tick_in_bar = first_note_time - bar_start_tick

            # Destination tick inside the bar
            target_tick_in_bar = (target_beat - 1) * unit_ticks

            shift_amount = int(target_tick_in_bar - tick_in_bar)

        elif 'move_beats' in op:
            # Move by a number of TS-based beats (denominator-aware)
            # Positive: move later, Negative: earlier
            # Use the TS at the first note position for unit size
            current_ts = miditoolkit.TimeSignature(4, 4, 0)
            for ts in sorted(midi_obj.time_signature_changes, key=lambda x: x.time):
                if ts.time <= first_note_time:
                    current_ts = ts
                else:
                    break
            unit_ticks = int(round(midi_obj.ticks_per_beat * 4 / current_ts.denominator))
            shift_amount = int(round(op['move_beats'] * unit_ticks))
        
        else:
            return

        # Shift all timed events
        for instrument in midi_obj.instruments:
            for note in instrument.notes:
                note.start += shift_amount
                note.end += shift_amount
        
        for key in midi_obj.key_signature_changes:
            key.time += shift_amount
            
        for ts in midi_obj.time_signature_changes:
            ts.time += shift_amount
        
        for tempo in midi_obj.tempo_changes:
            tempo.time += shift_amount

        # Remove events that are now before tick 0
        for instrument in midi_obj.instruments:
            instrument.notes = [n for n in instrument.notes if n.start >= 0]
        midi_obj.key_signature_changes = [k for k in midi_obj.key_signature_changes if k.time >= 0]
        midi_obj.time_signature_changes = [t for t in midi_obj.time_signature_changes if t.time >= 0]
        midi_obj.tempo_changes = [t for t in midi_obj.tempo_changes if t.time >= 0]

        # Update max_tick for accurate future seconds<->ticks mapping
        max_note_tick = 0
        for instrument in midi_obj.instruments:
            for note in instrument.notes:
                if note.end > max_note_tick:
                    max_note_tick = note.end
        max_meta_tick = 0
        if midi_obj.tempo_changes:
            max_meta_tick = max(max_meta_tick, max(t.time for t in midi_obj.tempo_changes))
        if midi_obj.time_signature_changes:
            max_meta_tick = max(max_meta_tick, max(t.time for t in midi_obj.time_signature_changes))
        if midi_obj.key_signature_changes:
            max_meta_tick = max(max_meta_tick, max(k.time for k in midi_obj.key_signature_changes))
        midi_obj.max_tick = max(max_note_tick, max_meta_tick)

    except Exception as e:
        print(f"Error handling start beat shift for op {op}: {e}")


def _build_time_signature_segments(midi_obj):
    ts_changes = sorted(midi_obj.time_signature_changes, key=lambda x: x.time)

    deduped = []
    for ts in ts_changes:
        ts_time = int(ts.time)
        if deduped and deduped[-1]['start'] == ts_time:
            deduped[-1]['numerator'] = ts.numerator
            deduped[-1]['denominator'] = ts.denominator
        else:
            deduped.append({
                'start': ts_time,
                'numerator': ts.numerator,
                'denominator': ts.denominator
            })

    if not deduped or deduped[0]['start'] != 0:
        deduped.insert(0, {'start': 0, 'numerator': 4, 'denominator': 4})

    segments = []
    ppq = max(1, int(midi_obj.ticks_per_beat))
    for entry in deduped:
        denominator = entry['denominator']
        unit_ticks = int(round(ppq * 4 / denominator)) if denominator else ppq
        if unit_ticks <= 0:
            unit_ticks = ppq
        segments.append({
            'start': int(entry['start']),
            'numerator': entry['numerator'],
            'denominator': denominator,
            'unit': unit_ticks,
            'end': None,  # filled below
            'cumulative_beats': 0,
            'beats': None
        })

    for idx in range(len(segments) - 1):
        segments[idx]['end'] = segments[idx + 1]['start']
        seg_length = max(0, segments[idx]['end'] - segments[idx]['start'])
        segments[idx]['beats'] = seg_length // segments[idx]['unit'] if segments[idx]['unit'] else 0

    cumulative = 0
    for segment in segments:
        segment['cumulative_beats'] = cumulative
        if segment['beats'] is not None:
            cumulative += segment['beats']

    return segments


def _tick_to_global_beat_info(tick, segments):
    tick = int(tick)
    for segment in segments:
        unit = segment['unit']
        start = segment['start']
        end = segment['end']
        if tick < start:
            return segment['cumulative_beats'] + 1, start, 0
        if end is not None and tick >= end:
            continue
        offset = max(0, tick - start)
        beat_index_in_segment = offset // unit if unit else 0
        beat_start_tick = start + beat_index_in_segment * unit
        offset_within_beat = tick - beat_start_tick
        global_idx = segment['cumulative_beats'] + beat_index_in_segment + 1
        return global_idx, beat_start_tick, offset_within_beat

    last = segments[-1]
    unit = last['unit'] or 1
    start = last['start']
    offset = max(0, tick - start)
    beat_index_in_segment = offset // unit
    beat_start_tick = start + beat_index_in_segment * unit
    offset_within_beat = tick - beat_start_tick
    global_idx = last['cumulative_beats'] + beat_index_in_segment + 1
    return global_idx, beat_start_tick, offset_within_beat


def _global_beat_to_tick(beat_index, segments):
    if beat_index < 1:
        beat_index = 1
    target_zero_based = beat_index - 1

    for segment in segments:
        unit = segment['unit'] or 1
        start = segment['start']
        beats_before = segment['cumulative_beats']
        beats_in_segment = segment['beats']

        if target_zero_based < beats_before:
            return start

        offset_inside_segment = target_zero_based - beats_before
        if beats_in_segment is None or offset_inside_segment < beats_in_segment:
            return start + offset_inside_segment * unit

    last = segments[-1]
    unit = last['unit'] or 1
    offset_inside_segment = target_zero_based - last['cumulative_beats']
    if offset_inside_segment < 0:
        offset_inside_segment = 0
    return last['start'] + offset_inside_segment * unit


def _shift_timed_events(midi_obj, shift_amount):
    if shift_amount == 0:
        return

    def shift_and_filter(events, clamp_zero=False):
        updated = []
        for event in events:
            event.time += shift_amount
            if clamp_zero and event.time < 0:
                event.time = 0
            if event.time >= 0:
                updated.append(event)
        return sorted(updated, key=lambda e: e.time)

    for instrument in midi_obj.instruments:
        for note in instrument.notes:
            note.start += shift_amount
            note.end += shift_amount
        instrument.notes = [n for n in instrument.notes if n.end > 0]

        for cc in instrument.control_changes:
            cc.time += shift_amount
        instrument.control_changes = [cc for cc in instrument.control_changes if cc.time >= 0]

        for pb in instrument.pitch_bends:
            pb.time += shift_amount
        instrument.pitch_bends = [pb for pb in instrument.pitch_bends if pb.time >= 0]

        for pedal in instrument.pedals:
            pedal.start += shift_amount
            pedal.end += shift_amount
        instrument.pedals = [p for p in instrument.pedals if p.end > 0]

    midi_obj.tempo_changes = shift_and_filter(midi_obj.tempo_changes, clamp_zero=True)
    midi_obj.time_signature_changes = shift_and_filter(midi_obj.time_signature_changes, clamp_zero=True)
    midi_obj.key_signature_changes = shift_and_filter(midi_obj.key_signature_changes, clamp_zero=True)
    midi_obj.markers = shift_and_filter(midi_obj.markers, clamp_zero=True)

    if not midi_obj.time_signature_changes:
        midi_obj.time_signature_changes.append(miditoolkit.TimeSignature(4, 4, 0))
    else:
        midi_obj.time_signature_changes.sort(key=lambda x: x.time)
        first_ts = midi_obj.time_signature_changes[0]
        if first_ts.time != 0:
            first_ts.time = 0

    if midi_obj.tempo_changes:
        midi_obj.tempo_changes.sort(key=lambda x: x.time)
        first_tempo = midi_obj.tempo_changes[0]
        if first_tempo.time != 0:
            first_tempo.time = 0

    for instrument in midi_obj.instruments:
        instrument.notes.sort(key=lambda n: n.start)
        instrument.control_changes.sort(key=lambda c: c.time)
        instrument.pitch_bends.sort(key=lambda p: p.time)
        instrument.pedals.sort(key=lambda p: p.start)


def handle_move_to_global_beat(midi_obj, op):
    try:
        # Require 'to_beat' specifying the destination global beat index (1-based)
        destination_beat = int(op['to_beat'])

        # If there are no notes, nothing to move
        has_notes = any(len(instr.notes) > 0 for instr in midi_obj.instruments)
        if not has_notes:
            return

        # Current first note tick
        first_note_tick = min([
            note.start
            for note in midi_obj.instruments[0].notes
        ])

        segments = _build_time_signature_segments(midi_obj)

        _, _, _ = _tick_to_global_beat_info(first_note_tick, segments)
        dest_tick = _global_beat_to_tick(destination_beat, segments)

        shift_amount = int(dest_tick - first_note_tick)

        if shift_amount == 0:
            return

        _shift_timed_events(midi_obj, shift_amount)

        max_note_tick = 0
        for instrument in midi_obj.instruments:
            for note in instrument.notes:
                if note.end > max_note_tick:
                    max_note_tick = note.end
        max_meta_tick = 0
        if midi_obj.tempo_changes:
            max_meta_tick = max(max_meta_tick, max(t.time for t in midi_obj.tempo_changes))
        if midi_obj.time_signature_changes:
            max_meta_tick = max(max_meta_tick, max(t.time for t in midi_obj.time_signature_changes))
        if midi_obj.key_signature_changes:
            max_meta_tick = max(max_meta_tick, max(k.time for k in midi_obj.key_signature_changes))
        midi_obj.max_tick = max(max_note_tick, max_meta_tick)

    except Exception as e:
        print(f"Error handling move_to global beat for op {op}: {e}")


def process_midi_file(filepath, operations):
    try:
        midi_obj = miditoolkit.MidiFile(filepath)
        
        for op in operations:
            if op['operation'] == 'change_time_signature':
                handle_time_signature_change(midi_obj, op)
            elif op['operation'] == 'add_key_change':
                handle_key_signature_change(midi_obj, op)
            # elif op['operation'] == 'shift_start_beat':
            #     handle_start_beat_shift(midi_obj, op)
            elif op['operation'] == 'shift_start_beat':
                handle_move_to_global_beat(midi_obj, op)
                
        return midi_obj

    except Exception as e:
        print(f"Failed to process {os.path.basename(filepath)}: {e}")
        return None

# --- Main Execution ---

def main():
    if not os.path.exists(SRC_DIR):
        print(f"Source directory not found: {SRC_DIR}")
        return

    if not os.path.exists(OPERATIONS_FILE):
        print(f"Operations file not found: {OPERATIONS_FILE}")
        return

    os.makedirs(DST_DIR, exist_ok=True)

    with open(OPERATIONS_FILE, 'r', encoding='utf-8') as f:
        operations_data = json.load(f)

    midi_files = [f for f in os.listdir(SRC_DIR) if f.endswith('.mid')]

    for filename in tqdm(midi_files, desc="Processing MIDI files"):
        src_path = os.path.join(SRC_DIR, filename)
        dst_path = os.path.join(DST_DIR, filename)
        
        file_id = str(int(os.path.splitext(filename)[0]))

        if file_id in operations_data:
            processed_midi = process_midi_file(src_path, operations_data[file_id])
            if processed_midi:
                processed_midi.dump(dst_path)
        else:
            shutil.copy2(src_path, dst_path)
            
    print(f"\\nProcessing complete. Files are saved in '{DST_DIR}'.")

if __name__ == '__main__':
    main()
