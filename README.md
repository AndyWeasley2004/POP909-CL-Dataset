# POP909-CL Dataset

POP909-CL is a chord-labelled extension of the original [POP909](https://github.com/music-x-lab/POP909-Dataset) corpus, intended to support chord recognition, automatic accompaniment, and music theory research. The repository combines expert-reviewed chord annotations with cleaned, metadata-corrected MIDI files while preserving backwards compatibility with the POP909 timing grid.

## Dataset Structure

- **`POP909-24-bin-midi/`** – Original POP909 release quantized to 24 bins per beat. Included for reference and reproducibility against the prior benchmark corpus.
- **`POP909_chord_annotated/`** – Raw expert-annotated MIDI files retaining the additional algorithmic chord track used during curation.
- **`POP909_chord_annotated_cleaned/`** – Cleaned annotations. Track 1 carries the musical score; Track 2 carries the corrected chord progression. All algorithmically generated chord tracks have been removed.
- **`POP909_processed/`** – Final curated files enriched with consistent metadata (time/key signatures, start-beat alignment, tempo sanity checks). These are the recommended assets for most downstream tasks.
- **`midi_operations.json`** – Machine-readable log of every manual edit applied during curation (time signature updates, key changes, start-beat shifts, etc.).
- **`process.py`** – Reproducible processing script that ingests the cleaned annotations together with `midi_operations.json` and regenerates the processed set.

## Processing Workflow

1. Start from the raw expert annotated files in `POP909_chord_annotated/`.
2. Remove algorithmic chord tracks and normalize channel assignments → `POP909_chord_annotated_cleaned/`.
3. Apply the operations logged in `midi_operations.json` using `process.py` to correct time signatures, add key changes, and align global start beats to get `POP909_processed`
4. Manually verify the metadata adjusted is consistent with expert annotations.

Regenerating the processed corpus:

```bash
python process.py
```

The script expects the cleaned directory and operations file to be present in the repository root. Output MIDI files are written to `POP909_processed/`.

5. (Optional) You can use the following script to extract chord labels and their onset beat from the chord track in MIDI:

```bash
python process_pop909.py
```

## Annotation Conventions

- Track 1 (`channel 0`) is the musical score (melody, accompaniment, and rhythm combined in one track as released in POP909).
- Track 2 (`channel 1`) holds human-corrected chord symbols aligned to beats.
- Files follow the POP909 24-grid quantization to ensure interoperability with existing analyses.
- Time signature and key signature change events are explicitly encoded; people should read these meta-events.

## Using the Dataset

- For chord recognition modelling, rely on `POP909_processed/` or `POP909_processed.zip` to benefit from metadata corrections.
- When comparing against legacy POP909 benchmarks, reference `POP-24-bin-midi/`.
- Research replicating annotation decisions can consult `midi_operations.json` for per-piece transformations.

## Problematic Pieces and Known Issues

Document pieces requiring special handling (e.g., unresolved time signatures, ambiguous chord labels, missing metadata).

- *518.mid*: Left and right hands have misaligned downbeats in quantization version, so we keep the algorithm-extracted labels.
- *620.mid*: Left and right hands are potentially misaligned.

## Citation

If you use this resource, please cite this curated release:

```BibTeX
@inproceedings{bachi2025,
    author = {Mingyang Yao, Ke Chen, Shlomo Dubnov, Taylor Berg-Kirkpatrick},
    title = {BACHI: Boundary-Aware Symbolic Chord Recognition Through Masked Iterative Decoding on Pop and Classical Music},
    booktitle = {arXiv},
    year = {2025}
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