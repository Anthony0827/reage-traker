# Insult Detection Specification

## Purpose

Offline Spanish speech-to-text via Vosk that counts insults in real time during a session. Parallel to `AudioMonitor` (scream detection) — same lifecycle API (`start/stop/get_summary`), same privacy constraint: **no transcript is ever displayed**.

## Requirements

### Requirement: Detector Lifecycle

The `InsultDetector` in `src/insult_detector.py` MUST expose `start()`, `stop()`, `get_summary()`, `list_insults()`, and `reset()` following the same API contract as `AudioMonitor`.

- `start()` SHALL open a sounddevice `InputStream` at 16 kHz mono int16. If the stream fails (e.g., device busy or missing), it MUST set `last_error`, log the failure, and return `False` — never abort the session.
- `stop()` MUST close the stream and reset live state (`level`, `is_insult_active`).
- `get_summary()` MUST return `{insult_count, insult_peak_count, insult_model_name, last_error}`.
- `list_insults()` MUST return the list of matched insult forms from the current session.
- `reset()` MUST zero the counters without closing the stream.

#### Scenario: Happy path — normal lifecycle

- GIVEN a user starts a game session with the `insults` sensor enabled
- WHEN the launcher creates and calls `detector.start()`
- THEN the detector opens a 16 kHz mono audio stream via sounddevice
- AND `start()` returns `True`
- AND `get_summary()` returns `insult_count=0` and `last_error=""`

#### Scenario: Stream start fails — non-fatal fallback

- GIVEN the sounddevice InputStream cannot open (e.g., device already in use by another process)
- WHEN `detector.start()` is called
- THEN it MUST set `last_error` to the failure reason
- AND return `False`
- AND the session MUST continue with the remaining sensors (emotions, scream)

#### Scenario: Model not found — graceful degradation

- GIVEN the Vosk model directory (`RAGE_VOSK_MODEL` or `models/vosk-es`) does not exist or is invalid
- WHEN `start()` attempts to load `vosk.KaldiRecognizer`
- THEN it MUST log the error, set `last_error`, and return `False`
- AND the checkbox in the launcher MUST remain enabled (user can still toggle)

### Requirement: Audio Processing Pipeline

The detector MUST process audio in a sounddevice callback: receive int16 blocks, feed them to `vosk.KaldiRecognizer`, tokenize each final JSON result, lower-case and strip punctuation, then match against the loaded lexicon.

Matching SHALL use a built-in Spanish stemmer (pure Python, no NLTK dependency) that strips suffixes `{-os,-as,-o,-a,-es,-amos,-áis,-an,-en,-ar,-er,-ir,-ando,-iendo}` and compares the stem against precomputed lexicon stems. Each match MUST increment `_insult_count` by 1 — **no debounce, no deduplication per window**.

#### Scenario: Happy path — known insult recognized

- GIVEN the detector is running and the Vosk model is loaded
- WHEN the user speaks "idiota" (a known insult in `data/insultos.csv`)
- AND `vosk.KaldiRecognizer` produces a JSON partial/final containing "idiota"
- THEN the stemmer matches the stem against the lexicon
- AND `insult_count` increments by 1

#### Scenario: Stem variant match

- GIVEN the lexicon contains "gilipollas" (base form)
- WHEN the user speaks "gilipollas" and the transcript tokenizes to "gilipollas"
- THEN the stemmer strips "-as" → stem "gilipoll"
- AND since the lexicon was pre-stemmed to "gilipoll" at load time
- AND a match is found
- THEN `insult_count` increments by 1

#### Scenario: No match — no false positive

- GIVEN the user speaks "gracias" (not in the insult lexicon)
- WHEN Vosk returns the transcript
- THEN the stemmer produces stem "graci"
- AND no lexicon stem matches
- AND `insult_count` does NOT change

#### Scenario: Punctuation stripped before matching

- GIVEN the Vosk transcript contains "¡idiota!"
- WHEN `start()` processes the token
- THEN punctuation `¡`, `!` is stripped
- AND the remaining "idiota" is stemmed and matched
- AND `insult_count` increments by 1

### Requirement: Privacy Constraint — No Transcript Leakage

The detector MUST NOT display, log, or store any partial or final transcript text. The only observable outputs are `insult_count`, `insult_peak_count`, and `list_insults()` (which returns only matched base forms, not the raw transcript).

- HUD, CSV, dashboard, and console output MUST show **only counts**, never raw text.
- The `print()` or logging of any transcript fragment is a spec violation.

#### Scenario: Transcript never reaches HUD

- GIVEN the detector matched 3 insults during a session
- WHEN the HUD pill renders
- THEN it MUST show `INSULTOS x3`
- AND no recognized words appear anywhere on the frame

#### Scenario: Transcript never reaches logs

- GIVEN the detector logs diagnostic info during a session
- WHEN `grep`-ing the console output for any recognized word
- THEN no matches SHALL be found

### Requirement: Lexicon Loading

The detector MUST load insult base forms from `data/insultos.csv` (one base form per line, UTF-8) at initialization. The lexicon SHALL be pre-stemmed at load time for O(1) match lookups. If the file is missing or empty, the detector MUST log a warning, set `last_error`, and continue with an empty lexicon (no detections possible).

#### Scenario: Missing lexicon file

- GIVEN `data/insultos.csv` does not exist
- WHEN the `InsultDetector` initializes
- THEN it MUST log a warning: "Insult lexicon not found"
- AND set `last_error` accordingly
- AND `get_summary()` returns `insult_count=0`

#### Scenario: Empty lexicon

- GIVEN `data/insultos.csv` exists but is empty
- WHEN the detector loads it
- THEN the lexicon set is empty
- AND any spoken words produce zero matches

### Requirement: Live State

The detector MUST expose `level` (always `0.0` — no volume level), `is_insult_active` (boolean, reflecting whether the last partial result contained a match), and `last_error` (string, empty on success).

#### Scenario: Insult active state

- GIVEN the detector is running
- WHEN the last partial Vosk result contains a matched insult
- THEN `is_insult_active` MUST be `True`
- AND after the next partial with no match, it MUST return to `False`