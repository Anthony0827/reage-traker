# Tasks: Real-time Insult Detection (Vosk, Spanish)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~850 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

PR split — phases 1-2, 3-5, 6-9. Phase 10 tests ship with their code.

## Phase 1: Setup

- [ ] 1.1 Add `vosk` to `requirements.txt`
- [ ] 1.2 Create `data/insultos.csv` lexicon (~50 base forms)
- [ ] 1.3 `scripts/download_vosk_model.py` — URL+checksum+retry → `models/vosk-es/`
- [ ] 1.4 Gitignore `models/`+`data/models/`, add `.gitkeep`
- [ ] 1.5 `pip install vosk` smoke (1.1)

## Phase 2: Core Module

- [ ] 2.1 `SpanishStemmer.stem()` suffix stripper
- [ ] 2.2 `__init__` + `_load_lexicon()`: UTF-8 CSV, pre-stem at load
- [ ] 2.3 `_callback()`: feed KaldiRecognizer, tokenize, strip punct, stem-match
- [ ] 2.4 `start()`: 16kHz stream, load model
- [ ] 2.5 `stop()`, `reset()`, `get_summary()` (4 keys), `list_insults()`
- [ ] 2.6 Live state: level=0.0, is_insult_active, last_error

## Phase 3: Data Migration

- [ ] 3.1 `INSULT_FIELDS` (count, peak, model_name) after `SCREAM_FIELDS` in `SESSION_FIELDS`
- [ ] 3.2 `_migrate_sessions_schema()`: atomic `tempfile.mkstemp`, defaults `0,0,""`
- [ ] 3.3 `save_session()` persist `insult_*`; `get_game_stats()`+`global_stats` compute `total_insults`

## Phase 4: Session Runner

- [ ] 4.1 `RAGE_PER_INSULT = 0.3` + `_INSULT_KEYS` tuple
- [ ] 4.2 `_fold_insults_into_rage(summary, weight)` — mirror scream fold
- [ ] 4.3 `want_insults` branch: import + start, fallback (2.6)
- [ ] 4.4 Collect `insult_summary`, merge `_INSULT_KEYS`, `stop()`
- [ ] 4.5 Call fold only when `emotions AND insults` (4.2, 4.4)
- [ ] 4.6 Add `insults` to `--sensors` choices

## Phase 5: Launcher UI

- [ ] 5.1 `insult_var` + `INSULTOS (beta)` checkbox (mirror `scream_var`)
- [ ] 5.2 Include `insults` in subprocess `--sensors` + sensor-list validation

## Phase 6: Camera HUD

- [ ] 6.1 Optional `insult_detector` in `EmotionDetector.__init__` (default None)
- [ ] 6.2 `_draw_mic_indicator()` renders `INSULTOS x{n}` pill
- [ ] 6.3 Pass `insult_detector` from `run_session()` to `EmotionDetector` (4.3, 6.2)

## Phase 7: Dashboard API

- [ ] 7.1 Expose `insult_count`, `insult_peak_count`, `insult_model_name` per session (3.3)
- [ ] 7.2 Add `total_insults` to `global_stats`
- [ ] 7.3 Build `insults_leaderboard` (games ranked by total)

## Phase 8: Dashboard UI

- [ ] 8.1 `INSULTOS POR JUEGO` tile (7.3)
- [ ] 8.2 Insult heat chip (8.1)
- [ ] 8.3 Empty state "Sin datos de insultos" (8.1)
- [ ] 8.4 `total_insults` vital card (7.2)

## Phase 9: Documentation

- [ ] 9.1 README: `vosk` install + `download_vosk_model.py` (1.3)
- [ ] 9.2 README: `RAGE_VOSK_MODEL` env + privacy guarantee

## Phase 10: Testing

- [ ] 10.1 Unit: `SpanishStemmer` fixture pairs (gilipollas, idiota, gracias, casar) (2.1)
- [ ] 10.2 Unit: `get_summary()` shape/types, mocked sounddevice (2.5)
- [ ] 10.3 Unit: `_fold_insults_into_rage()` (4.2)
- [ ] 10.4 Unit: migration idempotency (3.2)
- [ ] 10.5 Integration: WAV, 3 insults → `insult_count >= 2` (1.5, 2.6)
- [ ] 10.6 E2E: `--sensors emotions insults` writes row + HUD pill (4.6, 6.3)
