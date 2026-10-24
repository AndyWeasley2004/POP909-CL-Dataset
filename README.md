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
- **`annotations/corrections.csv`** – Per-piece downbeat and meter corrections made after the expert annotation.
- **`scripts/`** – Utilities for checking the release and writing chord markers.
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

- `status`: `released` or `missing` (see [missing pieces](#missing-pieces)).
- `initial_key`, `initial_meter`, `ppq`, `key_changes`, `meter_changes` (as `key@tick`).
- `total_shift_ticks`: the tick offset from the POP909 24-bin timeline.
- `flags`: caveats worth checking before relying on a piece (see below).

## Missing Pieces

| Piece | Reason |
| --- | --- |
| 553 | The annotated score was a copy of 543 (#1); no annotation of the genuine 553 exists |
| 367 | The annotated file has no chord track |
| 658 | The annotated file has no score track, so its chords cannot be aligned |

## Known Issues

10 released pieces carry `flags` in the metadata, e.g. a single bar of a different meter, or an approximate meter change.

## What's Revised

- **Score.** Rebuilt from the POP909 24-bin quantization, keeping the original MELODY / BRIDGE / PIANO tracks and pedals.
- **Chords.** The expert chord annotation is aligned to the same 24-bin timeline.
- **Downbeat, meter and key.** Start beats, time signatures and key changes follow the expert annotation, applied on the original beat grid so that beats stay aligned with POP909.
- **Further corrections.** Some downbeat and meter errors the annotation missed were found by automatic detection and spot-checked by listening.
- **Issues #1 and #2.** 553 (a duplicate of 543) is removed, and `043 .mid` is renamed.

**Automatic error detection.** For every beat we combine simple evidence: POP909's own downbeat estimates, accents in the score (bass, long notes, velocity), harmonic change, and where the annotated chords change. A small model learned from expert-checked pieces then estimates the most likely downbeat position and meter, and flags pieces, or sections of pieces, that disagree with the current bar lines.

## Chord Labels

The `CHORDS` track spells each chord as notes. Labels are derived by simple template matching of the sounding pitch classes against triad and seventh-chord templates; the lowest note gives the bass. `POP909_chord_labels/NNN.csv` lists `offset_qb` (onset in quarter notes), `root`, `quality`, `bass` and `local_key`, and the same labels appear as markers in each MIDI file. To regenerate them:

```bash
python process_pop909.py --pop909-root POP909_processed --out data_root/all_data_collection
```

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
