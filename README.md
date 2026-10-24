# POP909-CL Dataset

[Paper](https://arxiv.org/abs/2510.06528) | [Demo Page](https://andyweasley2004.github.io/BACHI/) | [POP909-CL Dataset](https://github.com/AndyWeasley2004/POP909-CL-Dataset) | [Model Weight & Data](https://huggingface.co/datasets/Itsuki-music/BACHI_Chord_Recognition)

POP909-CL is a chord-labelled extension of the original [POP909](https://github.com/music-x-lab/POP909-Dataset) corpus, intended to support chord recognition, automatic accompaniment, and music theory research. The repository combines expert-reviewed chord annotations with metadata-corrected MIDI files while preserving backwards compatibility with the POP909 24-bin timing grid. It is part of the release of the paper "BACHI: Boundary-Aware Symbolic Chord Recognition Through Masked Iterative Decoding on Pop and Classical Music". You can refer to details about this project [here](https://andyweasley2004.github.io/BACHI/)

## TL;DR
For anyone want to just use the data, please go to `POP909_processed/` subfolder (or `POP909_processed.zip`), which contains corrected MIDI with chord labels, and `POP909_processed/metadata.csv` for per-piece metadata.

## Dataset Highlight

### Key Improvements
- ✅ 40.6% of misaligned start beats corrected
- ✅ 14.2% of missing key signature changes added
- ✅ 2.6% of incorrect time signatures fixed
- ✅ ~35% of chord label errors corrected

### Statistics
- **Total tracks**: 906 of the 909 POP909 songs (see [missing pieces](#missing-pieces))
- **Format**: MIDI with aligned annotations
- **Annotations**: Chords, beats, keys, time signatures
- **Quality**: Professionally reviewed and corrected

### Example Correction

<img width="1549" height="584" alt="image" src="https://github.com/user-attachments/assets/a58dbbdc-e148-4090-bf8e-954e26c5be4f" />

## Dataset Structure

- **`POP909_processed/`** – The release: one `NNN.mid` per piece plus `metadata.csv` / `metadata.json`.
- **`POP909_processed.zip`** – The same folder, zipped.
- **`POP909_chord_labels/`** – One `NNN.csv` per piece with the chord labels derived from the `CHORDS` track (see [Chord labels](#chord-labels)).
- **`POP909_chord_annotated/`** – Raw expert-annotated MIDI files (merged score, algorithmic chord track, human chord track). The release takes the human chord track from here.
- **`POP909_chord_annotated_cleaned/`** – The raw files with the algorithmic chord track removed. Kept for reference.
- **`annotations/corrections.csv`** – Per-piece downbeat and meter corrections applied after the expert annotation, each marked as a listening check or a detector proposal.
- **`scripts/`** – `detect_errors.py` finds likely downbeat and meter errors and writes `POP909_processed/review.csv`; `add_chord_markers.py` writes the chord labels into the MIDI files as markers; `validate_release.py` checks the release against the 24-bin quantization and the annotated MIDI.
- **`process_pop909.py`** – Exports chord labels (`chord_symbol.csv`) and score-only MIDI for training.

## File Format

Each `POP909_processed/NNN.mid` is a type-1 MIDI file with five tracks:

| Track | Content |
| --- | --- |
| 0 `POP909-CL NNN` | Tempo, time signature and key signature events, and a marker with the chord label (e.g. `C#:m7/E`) at each chord onset |
| 1 `MELODY`, 2 `BRIDGE`, 3 `PIANO` | The three POP909 tracks, from the POP909 24-bin quantization, with the original sustain/sostenuto/soft pedals (CC64/66/67) |
| 4 `CHORDS` | Human-annotated chords, one sustained note per chord tone |

- **Timing.** One POP909 beat is 480 ticks and lasts 0.6 s in every file (the tempo of the 24-bin MIDI). Notes keep the 24-bin grid (20 ticks); notes the quantization collapsed to zero length last 1 tick. For every note, `output tick = 24-bin tick + total_shift_ticks` (see metadata).
- **Downbeats.** Bar lines follow the corrected downbeat. Each file is then moved by whole bars so that the earliest note falls in the first bar. For example, a 4/4 piece starting on beat 7 starts on beat 3. Whole-bar moves never change beat or bar alignment. No notes are cropped.
- **PPQ.** 892 files use PPQ 480, so a POP909 beat is a quarter note. In the 14 x/8 pieces a POP909 beat is an eighth note, so they use PPQ 960, except 092, whose beat is a dotted quarter (PPQ 320). Tempo is scaled to match, so playback speed and tick positions are the same as everywhere else, and `ticks / ticks_per_beat` always counts true quarter notes.
- **Pedals.** Pedal events from the original POP909 MIDI are mapped onto the same 24-bin grid as the notes. Pedal changes before the start are summarized at tick 0.
- **Keys and meters.** Read the key and time signature events on track 0, including changes during the piece.

## Metadata

`metadata.csv` has one row per piece (`metadata.json` adds full detail):

- `status`: `released` or `missing`; `reason` explains a missing piece.
- `initial_key`, `initial_meter`, `ppq`, `key_changes`, `meter_changes` (as `key@tick`).
- `downbeat_source`: where the downbeat correction comes from:
  - `workbook_downbeat_at_beat` (头拍于第N拍开始: beat N of the 24-bin timeline is the downbeat)
  - `annotator_shift` (the annotator moved the file by whole beats)
  - `workbook_remark_*` (pieces 003, 006)
  - `inferred_from_chords` (see flags)
  - `correction_listening` / `correction_detector` (from `annotations/corrections.csv`)
  - `none`
- `total_shift_ticks`: the tick offset from the POP909 24-bin timeline.
- `flags`: items worth checking before relying on a piece (see below).
- `workbook_remarks`: the annotator's remarks, e.g. wrong-note reports.

## Missing Pieces

| Piece | Reason |
| --- | --- |
| 553 | The annotated score was a copy of 543 (#1); no annotation of the genuine 553 exists |
| 367 | The annotated file has no chord track |
| 658 | The annotated file has no score track, so its chords cannot be aligned |

## Problematic Pieces and Known Issues

98 released pieces carry `flags` in the metadata, and `review.csv` lists the detector's opinion of every piece.

### Downbeat and meter corrections

The workbooks leave some pieces with a wrong downbeat or meter, mostly in 001–100, whose annotators rarely recorded downbeat fixes. `scripts/detect_errors.py` looks for them using the following evidence on every POP909 beat:
- POP909's own MIDI and audio downbeat estimates;
- accents in the score: velocity, bass onsets, long notes, onset density;
- harmonic change in the score;
- the human chord changes.

How each part works:
- **Downbeat.** A small conditional-logit model, trained on pieces 101–909 whose annotators set or checked the downbeat, scores each beat position in the bar as the downbeat. It agrees with those pieces 79% of the time in cross-validation; most disagreements are the beat-1-vs-beat-3 ambiguity of 4/4.
- **Meter.** Chord changes, bass onsets and long notes are compared at 3- vs 2/4-beat periodicity, together with POP909's beats per bar.

The detector agreed with every listening check:
- 020, 036, 283 and 029: downbeat one beat off;
- 662: downbeat on the last beat of the annotated bar;
- 855: 4/4, not 3/4;
- 635: a downbeat change at bar 29;
- the proposed versions of 071, 026 and four half-bar pieces (046, 574, 263, 519).

`annotations/corrections.csv` applies 73 per-piece corrections. The `source` column marks 13 as listening checks and 60 as detector proposals. Listening checks of 13 pieces found the detector's corrections generally sound right, so all of its proposals were applied:
- one-beat or half-bar offsets with probability ≥ 0.9;
- the remaining one-beat offsets with probability 0.8–0.9;
- half-bar offsets that reached 0.9 after retraining;
- meter changes backed by both periodicity and POP909's beats per bar;
- the clearest section shifts.
- **Meter:** 809, 821, 855 → 4/4; 034, 584, 744, 749, 756 → 3/4. The new downbeat is uncertain in 584, 821 and 855.
- **Downbeat, one beat:** 014, 020, 026, 029, 036, 037, 061, 066, 071, 072, 073, 077, 087, 089, 098, 157, 187, 225, 246, 247, 283, 366, 368, 369, 506, 592, 631, 662, 799, 869, 872, 887, 890. For 247 listening was inconclusive; its chords change once per bar, always on the old beat 4, throughout the piece.
- **Downbeat, half bar (beat 3 → beat 1):** 004, 017, 018, 046, 058, 064, 078, 096, 097, 195, 222, 262, 263, 277, 355, 363, 511, 519, 564, 574, 587, 629, 696, 698, 699, 748, 781, 875. In 263 and 363 this overrides the workbook's downbeat remark.
- **Section shifts**, written as single bars of another meter:
  - 635: bar 28 is 3/4 (listening check: the downbeat moves one beat earlier at bar 29);
  - 845: 3/4 at bar 59, 5/4 at bar 129;
  - 857: 3/4 at bar 51, 5/4 at bar 98;
  - 114: 3/4 at bar 34.

  For the detector's pieces, a beat-by-beat dynamic-programming pass places each odd bar where the downbeat evidence switches. On 635 it agreed with the listening check to within two bars.

When a correction moves the bar lines, key changes given as bar numbers move to the nearest new bar line. Pieces with meter changes inside the piece (172, 635, 845, 857, 114) are not scored by the detector.

Still open in `review.csv`:
- Lower-confidence proposals (probability < 0.9 after the latest retraining). Applying them would let the detector confirm its own earlier corrections, so they need listening first.
- **Section shifts** (`section_shifts` column, 35 pieces). These are 8-bar windows whose downbeat is one beat off from the rest of the piece, which suggests POP909's beat grid gained or lost a beat. Most have runs in both directions and are more likely syncopation. 063 (bars 18–49) is a special song and is left unchanged.

### Other flags

- **Workbook says the annotator moved the file by a different number of beats than the file shows (11 pieces).** The file's shift is used, since the chords were labelled on it and agree with it.
- **173, 176, 203, 231, 307:** the annotator moved these x/8 files by half a beat; the downbeat was taken from the chord rhythm.
- **172:** the 6/8 section (01:37–01:53) cannot be written exactly in a 4/4 file; its meter changes are approximate.
- **280, 369:** the meter (3/8) comes from the annotated MIDI; the workbook says 4/4.
- **051, 685:** the annotated score lacks 1–2 notes of the 24-bin score; the release keeps the full 24-bin score.
- **518:** not annotated, since the left and right hands disagree on the downbeat; its chords are the algorithmic labels.
- **620, 623:** the hands may be misaligned in the score.
- **113:** the initial key is missing from the workbook and is taken from the annotated MIDI.

## Processing Workflow

Every release file was built directly from the sources:

1. **Score.** MELODY, BRIDGE and PIANO from `POP09-PIANOROLL-24-bin-quantization.zip`, at 480 ticks per beat.
2. **Chords.** The human chord track from `POP909_chord_annotated/`. It is moved back by the annotator's own shift onto the 24-bin timeline. Nudges within 1/16 beat of a half-beat are snapped (most of these are in 016 and 688).
3. **Downbeat, meter, key.** Applied from the annotators' metadata workbooks:
   - Workbook times (mm:ss) refer to the annotators' DAW playback at 120 BPM, i.e. 2 POP909 beats per second.
   - Workbook bar numbers count 4-beat bars in the annotator's file.
   - Both were checked against where the chords change key.
4. **Corrections.** `annotations/corrections.csv` overrides the downbeat or meter where listening checks or the detector found errors. `downbeat_beat` is the beat index (modulo the bar) of the 24-bin timeline that is a downbeat; `odd_bars` such as `28:3/4` makes one bar a different meter.
5. **Normalization.** Whole-bar shift so the earliest note is in bar 1; pedals added; each written file reopened and checked note by note.
6. **Chord markers.** `scripts/add_chord_markers.py` writes each chord label into track 0.

**Error detection.** `scripts/detect_errors.py` scores each beat of a piece with simple downbeat evidence:
- POP909's own MIDI/audio downbeats;
- score accents: velocity, bass, long notes;
- harmonic change;
- the human chord changes.

A small model learned from the expert-checked pieces then picks the most likely downbeat position, and periodicity at 3 vs 2/4 beats suggests the meter. The same model on 8-bar windows finds sections whose downbeat shifts. A sample of proposals was checked by listening; since those sounded right, the rest were applied as well.

```bash
python scripts/validate_release.py --quantized /path/to/POP09-PIANOROLL-24-bin-quantization.zip
python scripts/detect_errors.py \
    --quantized /path/to/POP09-PIANOROLL-24-bin-quantization.zip \
    --original /path/to/POP909-Dataset/POP909
```

**Chord sanity check.** Across the release, a median 91% of the score's sounding pitch content consists of chord tones (minimum 76%). In 905 of 906 pieces the chords align best with the score with no shift; the exception, 859, is marginal and explained by melodic anticipation.

`--original` is the `POP909` folder of the [original repository](https://github.com/music-x-lab/POP909-Dataset). Requires `mido`, `miditoolkit` and `numpy`.

## Chord labels

The `CHORDS` track spells each chord as notes. A label is derived by simple template matching: the pitch classes sounding together are compared with the triad (M, m, o, +, sus2, sus4) and seventh (D7, M7, m7, /o7, o7, mM7, +7) templates over every possible root. The lowest note gives the bass, and the key comes from the key signature in effect. Pitch sets that match no template are skipped. `POP909_chord_labels/NNN.csv` lists `offset_qb` (onset in quarter notes), `root`, `quality`, `bass` and `local_key`, with `N` for silence. The same labels are written as MIDI markers.

To regenerate the labels (and score-only MIDI) from the release:

```bash
python process_pop909.py --pop909-root POP909_processed --out data_root/all_data_collection
```

## Changelog

**v2**
- Rebuilt from the 24-bin quantization with the original MELODY / BRIDGE / PIANO tracks and pedals, instead of one merged score track.
- Fixed start beats. The previous `process.py` moved the first note onto beat N instead of treating beat N as the downbeat, and snapped it onto the beat, which moved many pieces off the POP909 beat grid.
- Fixed key and meter changes given as times, which had been read at 100 instead of 120 BPM, and bar positions in files the annotators had moved.
- Corrected the downbeat or meter of 73 pieces that the annotation missed, found by listening checks and an evidence-based detector.
- Removed 553, whose score duplicated 543 (#1). Renamed `043 .mid` to `043.mid` (#2).
- Removed the historical `process.py` / `midi_operations.json`, whose start-beat handling was wrong.
- Added chord-label CSVs (`POP909_chord_labels/`) and chord markers in every MIDI file.

## Citation

If you use this resource, please cite this curated release:

```BibTeX
@inproceedings{bachi2025,
    author = {Mingyang Yao, Ke Chen, Shlomo Dubnov, Taylor Berg-Kirkpatrick},
    title = {BACHI: Boundary-Aware Symbolic Chord Recognition Through Masked Iterative Decoding on Pop and Classical Music},
    booktitle = {Proceedings of IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)},
    year = {2026}
}

```
along with original POP909 paper:

```BibTeX
@inproceedings{pop909-ismir2020,
    author = {Ziyu Wang* and Ke Chen* and Junyan Jiang and Yiyi Zhang and Maoran Xu and Shuqi Dai and Guxian Bin and Gus Xia},
    title = {POP909: A Pop-song Dataset for Music Arrangement Generation},
    booktitle = {Proceedings of 21st International Conference on Music Information Retrieval, {ISMIR}},
    year = {2020}
}
```
