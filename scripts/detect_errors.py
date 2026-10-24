"""Find likely downbeat and meter errors in a built POP909-CL release.

Evidence per POP909 beat (24-bin timeline):
  midi_db / audio_db  POP909's own downbeat estimates (npz beat array, beat_audio.txt)
  chord               a human chord change starts on the beat
  velocity, bass, long, onsets   accents in the score
  novelty             harmonic change in the score (chroma of 2 beats after vs before)

Downbeat: a conditional-logit model chooses which beat position in the bar is
the downbeat.  It is trained on pieces 101-909, whose annotators set or checked
the downbeat, and applied to every piece.  Meter: periodicity of chord changes,
bass onsets and long notes at 3- vs 2/4-beat lags.  Sections: the same model on
8-bar windows finds stretches whose downbeat is one beat off the rest of the piece.

Writes review.csv into the release folder; accepted proposals belong in
annotations/corrections.csv.

    python scripts/detect_errors.py --quantized ...24-bin-quantization.zip --original .../POP909
"""
import argparse
import csv
import io
import json
from pathlib import Path
import zipfile

import mido
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ('midi_db', 'audio_db', 'chord', 'velocity', 'bass', 'long', 'onsets', 'novelty')
# Annotators of 101-909 set or checked every downbeat; hands are unreliable in these.
UNTRUSTED = {'518', '620', '623'}
DOWNBEAT_CONFIDENCE = 0.9  # minimum model probability for an automatic correction
MIN_TRIPLE_EVIDENCE = 0.5  # |triple score| needed to propose a meter change


def beat_features(arrays, beat_times, audio, chord_beats):
    beat = arrays['beat']
    n = len(beat)
    features = {'midi_db': (beat[:, 3] == 0).astype(float)}
    audio_db = np.zeros(n)
    for t, position in audio:
        i = int(np.argmin(np.abs(beat_times - t)))
        if abs(beat_times[i] - t) < 0.12 and position == 1:
            audio_db[i] = 1
    features['audio_db'] = audio_db
    velocity, onsets, long_notes = np.zeros(n), np.zeros(n), np.zeros(n)
    lowest = np.full(n, 128.0)
    chroma = np.zeros((n, 12))
    for name in ('melody', 'bridge', 'piano'):
        for start, end, pitch, vel in arrays[name]:
            i = int(round(start))
            if 0 <= i < n and abs(start - i) < 1e-6:
                velocity[i] += vel
                onsets[i] += 1
                long_notes[i] += end - start >= 1.5
                if name != 'melody':
                    lowest[i] = min(lowest[i], pitch)
            for j in range(max(0, int(np.floor(start))), min(n, int(np.ceil(end)))):
                chroma[j, int(pitch) % 12] += min(end, j + 1) - max(start, j)
    features['velocity'] = velocity / np.maximum(onsets, 1)
    features['onsets'] = onsets
    features['long'] = long_notes
    features['bass'] = (lowest < 60).astype(float)
    novelty = np.zeros(n)
    for i in range(2, n - 2):
        before, after = chroma[i - 2:i].sum(0), chroma[i:i + 2].sum(0)
        if before.sum() and after.sum():
            novelty[i] = 1 - before @ after / np.linalg.norm(before) / np.linalg.norm(after)
    features['novelty'] = novelty
    chord = np.zeros(n)
    chord[[b for b in chord_beats if 0 <= b < n]] = 1
    features['chord'] = chord
    features['midi_beats_per_bar'] = int(np.bincount(beat[:, 5]).argmax())
    features['audio_beats_per_bar'] = int(audio[:, 1].max()) if len(audio) else 0
    return features


def design(features, bar_beats):
    """One row per candidate downbeat position (beat index mod bar), standardized contrasts."""
    rows = np.zeros((bar_beats, len(FEATURES)))
    for j, name in enumerate(FEATURES):
        x = features[name]
        profile = np.array([x[p::bar_beats].mean() for p in range(bar_beats)]) - x.mean()
        rows[:, j] = profile / (x.std() + 1e-9)
    return rows


def softmax(scores):
    p = np.exp(scores - scores.max())
    return p / p.sum()


def fit(items, l2=1e-2, steps=3000, rate=0.5):
    weights = np.zeros(len(FEATURES))
    for _ in range(steps):
        gradient = -l2 * weights
        for rows, label in items:
            gradient += rows[label] - softmax(rows @ weights) @ rows
        weights += rate * gradient / len(items)
    return weights


def triple_evidence(features):
    """> 0 when chord changes, bass onsets and long notes repeat every 3 beats."""
    def periodicity(lag):
        values = []
        for name in ('chord', 'bass', 'long'):
            x = features[name] - features[name].mean()
            if x.std():
                values.append((x[:-lag] * x[lag:]).mean() / x.var())
        return np.mean(values) if values else 0.0
    return periodicity(3) + periodicity(6) - periodicity(2) - periodicity(4)


def section_shifts(features, bar_beats, weights, downbeat, total_shift, bars=8, confidence=0.8):
    """Runs of >= 2 confident 8-bar windows whose downbeat is one beat (not half a bar) off.

    Such a run suggests a beat was gained or lost in POP909's beat grid; one
    whole-piece shift cannot fix it.  Returns 'bars A-B: downbeat on beat k' strings.
    """
    width = bars * bar_beats
    n = len(features['chord'])
    windows = []
    for start in range(0, n - width + 1, width):
        part = {k: v[start:start + width] if isinstance(v, np.ndarray) else v for k, v in features.items()}
        p = softmax(design(part, bar_beats) @ weights)
        best = int(p.argmax())
        offset = (best - downbeat) % bar_beats
        odd = offset and not (bar_beats % 2 == 0 and offset == bar_beats // 2)
        windows.append((start, best, offset) if part['chord'].sum() >= 4 and p[best] >= confidence and odd else None)
    runs, current = [], []
    for window in windows + [None]:
        if window and current and window[1] == current[-1][1]:
            current.append(window)
            continue
        if len(current) >= 2:
            first = max(1, (current[0][0] * 480 + total_shift) // (bar_beats * 480) + 1)
            runs.append(f'bars {first}-{first + bars * len(current) - 1}: downbeat on beat {current[0][2] + 1}')
        current = [window] if window else []
    return runs


def load_piece(sid, piece, release, archive, original):
    arrays = np.load(io.BytesIO(archive.read(f'POP09-PIANOROLL-24-bin-quantization/{sid}.npz')), allow_pickle=True)
    beat_times = np.loadtxt(original / sid / 'beat_midi.txt')[:, 0]
    audio = np.loadtxt(original / sid / 'beat_audio.txt').reshape(-1, 2)
    chord_beats, tick = [], 0
    for message in mido.MidiFile(release / f'{sid}.mid').tracks[4]:
        tick += message.time
        if message.type == 'note_on' and message.velocity:
            beat = tick - piece['total_shift_ticks']
            if beat % 480 == 0:
                chord_beats.append(beat // 480)
    return beat_features(arrays, beat_times, audio, chord_beats)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--quantized', type=Path, required=True)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--release', type=Path, default=ROOT / 'POP909_processed')
    args = parser.parse_args()
    pieces = {p['piece_id']: p for p in json.loads((args.release / 'metadata.json').read_text())['pieces']
              if p['status'] == 'released'}
    features = {}
    with zipfile.ZipFile(args.quantized) as archive:
        for sid, piece in pieces.items():
            features[sid] = load_piece(sid, piece, args.release, archive, args.original)

    def current(sid):  # beat index (mod bar) that the release treats as the downbeat
        return (-(pieces[sid]['total_shift_ticks'] // 480)) % pieces[sid]['beats_per_bar']
    # Pieces whose meter changes mid-piece have no single downbeat phase; they are not scored.
    single = {s for s, p in pieces.items() if len(p['meter_changes']) == 1}
    trusted = [s for s in single if int(s) > 100 and s not in UNTRUSTED]
    weights = fit([(design(features[s], pieces[s]['beats_per_bar']), current(s)) for s in trusted])
    print('feature weights:', dict(zip(FEATURES, np.round(weights, 2))))

    rows = []
    for sid, piece in pieces.items():
        f = features[sid]
        if sid not in single:
            rows.append({'piece_id': sid, 'meter': piece['initial_meter'], 'kind': 'meter changes in piece; not scored',
                         'auto_correct': False})
            continue
        triple = triple_evidence(f)
        bar_beats = piece['beats_per_bar']
        meter, proposed_meter = piece['initial_meter'], ''
        if bar_beats == 3 and triple < -MIN_TRIPLE_EVIDENCE and f['midi_beats_per_bar'] == 4:
            proposed_meter, bar_beats = '4/4', 4
        elif bar_beats in (2, 4) and triple > MIN_TRIPLE_EVIDENCE and f['midi_beats_per_bar'] == 6:
            proposed_meter, bar_beats = '3/4', 3
        p = softmax(design(f, bar_beats) @ weights)
        best = int(p.argmax())
        now = current(sid) if not proposed_meter else None
        if proposed_meter:
            kind = 'meter'
        elif best == now:
            kind = 'agree'
        else:
            offset = (best - now) % bar_beats
            kind = 'half-bar' if bar_beats % 2 == 0 and offset == bar_beats // 2 else 'off-by-one'
        auto = kind == 'meter' or (kind == 'off-by-one' and p[best] >= DOWNBEAT_CONFIDENCE)
        sections = [] if proposed_meter else section_shifts(f, bar_beats, weights, now, piece['total_shift_ticks'])
        rows.append({'piece_id': sid, 'meter': meter, 'proposed_meter': proposed_meter,
                     'current_downbeat_beat': '' if now is None else now, 'proposed_downbeat_beat': best,
                     'p_current': '' if now is None else round(float(p[now]), 3), 'p_proposed': round(float(p[best]), 3),
                     'kind': kind, 'auto_correct': auto, 'triple_evidence': round(float(triple), 2),
                     'pop909_midi_beats_per_bar': f['midi_beats_per_bar'],
                     'pop909_audio_beats_per_bar': f['audio_beats_per_bar'],
                     'section_shifts': '; '.join(sections)})
    with (args.release / 'review.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), restval='')
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for row in rows:
        key = f'{row["kind"]}{" (auto)" if row["auto_correct"] else ""}'
        summary[key] = summary.get(key, 0) + 1
    summary['section_shifts'] = sum(bool(row.get('section_shifts')) for row in rows)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
