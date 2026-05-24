# Design: Real-time Insult Detection (Vosk, Spanish)

## Technical Approach

Offline Spanish STT via Vosk running parallel to `AudioMonitor`. Both share a sounddevice `InputStream` at 16 kHz mono int16. `InsultDetector` mirrors `AudioMonitor`'s API (`start/stop/get_summary`), uses a pure-Python Spanish stemmer (no NLTK), and increments `insult_count` per lexicon match with **no debounce**. Privacy contract: no transcript text ever displayed.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Audio backend | Independent `sounddevice.InputStream` (16 kHz mono) | WASAPI tolerates dual streams on Windows; per spec, failure is non-fatal |
| Insult matching | Suffix-stripping stemmer + pre-stemmed lexicon set | O(1) lookup, pure Python, no NLTK dependency |
| Stemmer scope | Suffixes `{-os,-as,-o,-a,-es,-amos,-áis,-an,-en,-ar,-er,-ir,-ando,-iendo}` | Covers Spanish verb/person/number inflections for insult base forms |
| RAGE_PER_INSULT | `0.3` | User decision: conservative weight; 3.3 insults ≈ 1 angry face |
| Model path | `RAGE_VOSK_MODEL` env var, default `models/vosk-es` | Configurable; gitignored models directory |
| Lexicon | `data/insultos.csv` — one base form per line, UTF-8, pre-stemmed at load | No runtime stemming cost; hand-curated to avoid false positives |

## Data Flow

```
sounddevice InputStream (16kHz mono int16)
       │
       ├──→ AudioMonitor._callback() ──→ _process_block() ──→ get_summary()
       │                                                        │
       └──→ InsultDetector._callback() ──→ vosk.KaldiRecognizer ──→ tokenize
                                                                    │
                                                      lowercase + strip punctuation
                                                                    │
                                                      SpanishStemmer.stem()
                                                                    │
                                                      lexicon_set.match() ──→ insult_count++
                                                                    │
                                              get_summary() ──→ {insult_count, insult_peak_count, ...}
```

## InsultDetector Class

```python
class InsultDetector:
    BLOCK_SIZE = 1024  # frames per capture block

    def __init__(self, model_path: Optional[str] = None):
        self.level: float = 0.0          # always 0.0 (no volume)
        self.is_insult_active: bool = False
        self.last_error: str = ""
        self._insult_count: int = 0
        self._insult_peak_count: int = 0
        self._running: bool = False
        self._stream = None
        self._recognizer = None
        self._lexicon_stems: set = {}
        self._model_name: str = ""

    def start() -> bool: ...
    def stop() -> None: ...
    def reset() -> None: ...
    def get_summary() -> dict: ...
    def list_insults() -> list[str]: ...

class SpanishStemmer:
    SUFFIXES = ("-os","-as","-o","-a","-es","-amos","-áis","-an","-en","-ar","-er","-ir","-ando","-iendo")

    @staticmethod
    def stem(word: str) -> str: ...
```

### Sequence: `start()` lifecycle

```
Caller ──→ InsultDetector.start()
              │
              ├─ load RAGE_VOSK_MODEL env or default models/vosk-es
              ├─ vosk.Model(model_path)
              │     │── fail → last_error="model not found", return False
              ├─ vosk.KaldiRecognizer(model, 16000)
              ├─ _load_lexicon(data/insultos.csv)
              │     │── fail → log warning, last_error, continue with empty set
              ├─ pre-stem lexicon (compute stem for each entry)
              ├─ sounddevice.InputStream(16000, mono int16, callback=_callback)
              │     │── fail → last_error=str(exc), return False
              └─ return True
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/insult_detector.py` | Create | `InsultDetector` class, `SpanishStemmer`, lexicon loader |
| `src/session_runner.py` | Modify | Add `insults` sensor branch, `_fold_insults_into_rage()`, `_INSULT_KEYS`, `RAGE_PER_INSULT=0.3` |
| `src/launcher.py` | Modify | Add `insult_var` checkbox `INSULTOS (beta)`, pass `insults` in `--sensors` list |
| `src/camera.py` | Modify | Accept optional `insult_detector` arg; extend `_draw_mic_indicator()` with `INSULTOS x{n}` pill |
| `src/data_manager.py` | Modify | Append `INSULT_FIELDS` to `SESSION_FIELDS`; migrate via `tempfile.mkstemp` |
| `main.py` | Modify | Add `insults` to `--sensors` choices |
| `web/dashboard_server.py` | Modify | Expose `insult_count`, `insult_peak_count` per session; `total_insults` in `global_stats` |
| `web/dashboard.html` | Modify | Insult Leaderboard tile + heat chip + vital card |
| `data/insultos.csv` | Create | Lexicon (one base form per line, UTF-8) |
| `scripts/download_vosk_model.py` | Create | Download `vosk-model-small-es-0.42` to `models/vosk-es/` |
| `models/vosk-es/` | Create (gitignore) | Vosk model files |
| `requirements.txt` | Modify | Add `vosk` |

## API Contracts

### InsultDetector

```python
def start() -> bool:
    """Opens 16kHz mono InputStream. Returns True on success, False on failure.
    Sets last_error on failure. Non-fatal: session continues if this fails."""

def stop() -> None:
    """Closes stream, resets level/is_insult_active."""

def reset() -> None:
    """Zeros counters without closing stream."""

def get_summary() -> dict:
    """Returns {
        'insult_count': int,
        'insult_peak_count': int,
        'insult_model_name': str,
        'last_error': str
    }"""

def list_insults() -> list[str]:
    """Returns matched insult base forms from current session (not transcript)."""
```

### SpanishStemmer

```python
class SpanishStemmer:
    SUFFIXES = (...)

    @staticmethod
    def stem(word: str) -> str:
        """Strips longest matching Spanish suffix. Returns stemmed word."""
```

## Integration: session_runner.py

```python
def _fold_insults_into_rage(summary: dict, weight: float = 0.3) -> dict:
    insults = int(summary.get("insult_count", 0) or 0)
    if insults <= 0 or weight <= 0:
        return summary
    add = int(round(insults * weight))
    summary["angry_count"] += add
    summary["peak_rage_count"] += add
    # recompute percentages...
    return summary

# In run_session():
want_insults = "insults" in sensors
if want_insults:
    from src.insult_detector import InsultDetector
    insult_detector = InsultDetector()
    if not insult_detector.start():
        # log warning, continue without insults
        insult_detector = None

# After emotion detection:
if want_insults and insult_detector:
    insult_summary = insult_detector.get_summary()
    for key in _INSULT_KEYS:
        summary[key] = insult_summary.get(key, 0)
    insult_detector.stop()

# Fold insults into rage (only if emotions + insults, not insults-only)
if want_emotions and want_insults:
    summary = _fold_insults_into_rage(summary)
```

## Error Codes

| Error | Cause | Handling |
|-------|-------|----------|
| `last_error="stream: device busy"` | Other process using mic | Log + continue session without insults |
| `last_error="model not found"` | `RAGE_VOSK_MODEL` invalid | Log + checkbox stays enabled; graceful no-op |
| `last_error="lexicon not found"` | `data/insultos.csv` missing | Log warning, empty lexicon, continue |
| `last_error="vosk init failed"` | Model corrupted | Log + return False |
| Transcription timeout | vosk not returning results | No error set; `_insult_count` just doesn't increment |

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `SpanishStemmer.stem()` | Fixture with `(input, expected)` pairs: `("gilipollas","gilipoll")`, `("idiota","idiot")` |
| Unit | `InsultDetector.get_summary()` | Mock sounddevice; verify dict keys and types |
| Unit | `_fold_insults_into_rage()` | Fixture dict; assert angry_count and percentages |
| Integration | `InsultDetector` lifecycle | With real Vosk model on a 5-min WAV file with 3 known insults → expect `insult_count >= 2` |
| E2E | Full session with insults | `--sensors emotions insults`, verify CSV columns and HUD pill |

## Migration / Rollout

No destructive migration. CSV migration adds 3 columns (`insult_count`, `insult_peak_count`, `insult_model_name`) via `tempfile.mkstemp` atomic rewrite. Legacy rows get defaults `{0, 0, ""}` via `.get(key, default)`.

Rollback: disable `RAGE_VOSK_MODEL` or uncheck checkbox → feature dormant. All changes are additive; old CSV rows still load.

## Open Questions

- [ ] Should `list_insults()` ever be called from the UI? The spec says no transcript but `list_insults()` returns base forms — clarify if this is ever surfaced beyond debug.
- [ ] The proposal mentions `insults_leaderboard` as a separate tile in dashboard.html — confirm layout parity with scream leaderboard is acceptable.
