# Proposal: Real-time Insult Detection (Vosk, Spanish)

## Intent

Add a third sensor to RAGE TRACKER: **offline Spanish speech-to-text** that
counts insults spoken during a session, feeds them into the rage index with a
conservative weight, and surfaces the count in the HUD and dashboard. The
AudioMonitor screams path is loudness-based and ignores what the player actually
*said*; Vosk captures semantic rage. Beta scope: detection quality > completeness,
**no transcript is ever displayed** (privacy).

## Scope

### In Scope
- New `src/insult_detector.py` mirroring `AudioMonitor` API (`start/stop/get_summary`).
- Vosk 16 kHz mono small Spanish model (`vosk-model-small-es-0.42`, ~39 MB).
- Insult lexicon loaded from `data/insultos.csv` (one base form per line).
- Rule-based Spanish stem/lemma matching, no NLTK dependency.
- UI checkbox `INSULTOS (beta)` in `src/launcher.py` sensor panel.
- Live counter pill in HUD (counter-only, no transcript).
- Non-destructive CSV migration: `insult_count` + `insult_peak_count` added to
  `data/sessions.csv`; legacy rows backfilled with `0`.
- Dashboard exposure: per-session fields + Insult Leaderboard tile + heat chip.
- `_fold_insults_into_rage()` in `session_runner.py` with `RAGE_PER_INSULT = 0.3`.
- `insults` added to `--sensors` CLI choice list in `main.py`.

### Out of Scope
- Cloud STT or any network call (Vosk runs offline).
- Displaying recognized text anywhere (HUD, dashboard, logs).
- Language beyond Spanish.
- N+1/streaming precision tuning (good-enough for beta).
- Sentiment analysis beyond literal lexicon match.

## Capabilities

> First SDD cycle: `openspec/specs/` is empty, so all capabilities are **new**.

### New Capabilities
- `insult-detection`: Vosk-backed Spanish speech recognition producing per-session
  insult counts; lexicon, stem matcher, detector lifecycle, UI toggle, live HUD
  counter, privacy contract (no transcript leakage).
- `insult-analytics`: persistence of insult metrics in `sessions.csv`, exposure
  in the dashboard API, leaderboard + heatmap tile, and weighted folding into
  the rage index (`RAGE_PER_INSULT = 0.3`).

### Modified Capabilities
- None (no prior specs exist).

## Approach

1. **Audio**: open an independent sounddevice InputStream at 16 kHz mono int16
   alongside `AudioMonitor` (Windows WASAPI tolerates dual streams; if
   `start()` fails, log + continue with screams only — never abort the session).
2. **STT**: `vosk.KaldiRecognizer` with the small Spanish model loaded from a
   configurable path (`RAGE_VOSK_MODEL` env var, default `models/vosk-es`).
   Process each final JSON result, tokenize on whitespace, lowercase, strip
   punctuation.
3. **Matching**: built-in minimal Spanish stemmer strips the suffix set
   `{-os,-as,-o,-a,-es,-amos,-áis,-an,-en,-ar,-er,-ir,-ando,-iendo}` and
   compares the stem to the loaded lexicon stems (precomputed at load time).
   Every match increments `_insult_count` by 1 — **no debounce**, per decision.
4. **Lifecycle**: detector exposes `level` (always 0), `is_insult_active` (since
   last partial), `get_summary()` returning `{insult_count, insult_peak_count,
   insult_model_name}`. The peak reflects the max single-window hit count.
5. **HUD**: extend `_draw_mic_indicator` in `src/camera.py` with a second pill
   "INSULTOS x{n}" (counter only) when `insult_detector` is attached.
6. **Rage fold**: `_fold_insults_into_rage()` adds `int(round(count * 0.3))` to
   `angry_count` and `peak_rage_count`, then recomputes percentages. Only runs
   when emotions + insults (not in `insults`-only mode, same rule as screams).
7. **CSV migration**: append `INSULT_FIELDS = ["insult_count", "insult_peak_count"]`
   to `data_manager.SESSION_FIELDS`; defaults `{0, 0}`. Atomic rewrite via
   `tempfile.mkstemp` (same pattern as scream migration).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/insult_detector.py` | New | Detector class, stemmer, lexicon loader. |
| `src/session_runner.py` | Modified | `_fold_insults_into_rage`, `RAGE_PER_INSULT`, `_INSULT_KEYS`, `insults` sensor branch. |
| `src/launcher.py` | Modified | `insult_var` checkbox, conditional mic-preview, `--sensors insults` plumbed to subprocess. |
| `src/camera.py` | Modified | Optional `insult_detector` arg; HUD counter pill. |
| `src/data_manager.py` | Modified | `INSULT_FIELDS` appended, migration, `get_game_stats` totals. |
| `main.py` | Modified | `--sensors` choices include `insults`. |
| `data/insultos.csv` | New | Lexicon (one base form per line, UTF-8). |
| `data/sessions.csv` | Migrated | Two new columns, default 0. |
| `web/dashboard_server.py` | Modified | `insult_count` + `insult_peak_count` per session; `total_insults` in global stats. |
| `web/dashboard.html` | Modified | Insult Leaderboard tile + heat chip + vital card, parallel to scream UI. |
| `requirements.txt` | Modified | Add `vosk` line. |
| `models/vosk-es/` | New (gitignored) | Downloaded model path, documented in README. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Vosk false positives inflate rage | Med | Conservative `RAGE_PER_INSULT = 0.3`; beta label discourages over-trust. |
| Dual sounddevice stream conflicts on some Win drivers | Low-Med | Detector failure is non-fatal: log + continue session with screams. |
| Model download fails / wrong path | Med | Detector reports `last_error`; UI checkbox stays enabled but the session falls back. |
| Stemmer over-matches (e.g., "caso" ≈ "casa") | Med | Hand-curated lexicon ships pre-stemmed; stemmer is a best-effort, not source of truth. |
| Transcript leaks into logs/HUD | Low | `grep` guard: never call `print(partial)`; only emit counts and a redacted boolean. |
| Performance hit on low-end CPUs | Low | Small model (~39 MB) is CPU-friendly; documented as "beta". |

## Rollback Plan

The feature is fully additive. Rollback steps:
1. Set `RAGE_VOSK_MODEL=` (empty) or leave the checkbox off — feature is dormant.
2. Revert `src/insult_detector.py`, the modified files, and `requirements.txt`.
3. Leave `data/sessions.csv` untouched: new columns have defaults and are ignored
   by older code (`.get(key, 0)` pattern is already in `data_manager`).
4. Remove `data/insultos.csv` and the `models/` folder.
No destructive migration. No data loss possible.

## Dependencies

- New: `vosk` (Python package, ~1 MB) + `vosk-model-small-es-0.42` (39 MB, manual
  download or script; not pip-installable).
- Spanish stemmer: pure-Python, no NLTK.
- `sounddevice` is already a hard dep (no change).
- OS: Windows/macOS/Linux unchanged from existing requirements.

## Success Criteria

- [ ] `pip install vosk` + model download documented in `README.md` (or setup script).
- [ ] A 5-minute recorded WAV with 3 known insults yields `insult_count >= 2`
  (allowing 1 misrecognition) on a developer laptop.
- [ ] `INSULTOS (beta)` checkbox in launcher starts/stops the detector without
  breaking the existing scream sensor.
- [ ] HUD shows `INSULTOS x{n}` pill in real time; no transcript text appears
  anywhere in the UI, logs, or CSV.
- [ ] `sessions.csv` migrates in place; old rows still load with `insult_count=0`.
- [ ] Dashboard exposes `total_insults`, per-session counts, and an insult
  leaderboard that mirrors the scream leaderboard layout.
- [ ] `_fold_insults_into_rage(0.3)` raises `angry_count` by the expected amount
  and updates percentages (unit-testable with a fixture dict).
- [ ] No regression: a session with only `scream` sensor behaves identically to
  pre-change.
