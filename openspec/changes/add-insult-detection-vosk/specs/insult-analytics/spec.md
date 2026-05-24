# Insult Analytics Specification

## Purpose

Persist insult detection metrics to `data/sessions.csv`, expose them via the dashboard API, render a counter-only pill in the HUD, and fold insult counts into the rage index. Follows the same pattern as the scream/`AudioMonitor` integration in `data_manager.py`, `dashboard_server.py`, and `camera.py`.

## Requirements

### Requirement: Non-Destructive CSV Schema Migration

The `INSULT_FIELDS` MUST be appended to `DataManager.SESSION_FIELDS` at the end, after `SCREAM_FIELDS`. The migration MUST follow the existing atomic pattern: read existing rows, write to a `tempfile.mkstemp`, then `os.replace` the original. Legacy rows without the new columns MUST default to `0`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `insult_count` | int | 0 | Total insult matches in the session |
| `insult_peak_count` | int | 0 | Max single-window matches |
| `insult_model_name` | str | "" | Vosk model identifier used |

#### Scenario: Fresh CSV — schema created

- GIVEN `data/sessions.csv` does not exist
- WHEN `DataManager.__init__()` runs
- THEN it MUST create the file with the full `SESSION_FIELDS` header including the insult columns
- AND a newly saved row with only scream data defaults `insult_count=0`

#### Scenario: Existing CSV — migration adds columns

- GIVEN `data/sessions.csv` has the old schema (no `insult_count` column)
- WHEN `DataManager.__init__()` runs
- THEN `_migrate_sessions_schema()` MUST detect the missing columns
- AND rewrite the file atomically via `tempfile.mkstemp`
- AND all existing rows MUST have `insult_count=0` and `insult_peak_count=0`

#### Scenario: Migration is idempotent

- GIVEN `data/sessions.csv` already has the insult columns
- WHEN `DataManager.__init__()` runs
- THEN `_migrate_sessions_schema()` MUST detect the complete header
- AND return immediately without rewriting

### Requirement: Rage Index Folding

A `_fold_insults_into_rage()` function in `session_runner.py` MUST add `int(round(insult_count * 0.3))` to `angry_count` and `peak_rage_count`, then recompute happy/angry/neutral percentages. This MUST only run when BOTH `emotions` and `insults` sensors are active (same rule as scream folding — not in insults-only mode).

- `RAGE_PER_INSULT = 0.3` is the weight constant.
- The fold MUST run AFTER `_fold_screams_into_rage()` when both scream and insults are active.

#### Scenario: Insults fold with emotions

- GIVEN a session summary with `happy_count=10, angry_count=5, neutral_count=5, insult_count=3`
- WHEN `_fold_insults_into_rage(summary, weight=0.3)` is called
- THEN `int(round(3 * 0.3))` = `1` is added to `angry_count`
- AND `angry_count` becomes 6
- AND `peak_rage_count` increases by 1
- AND `angry_percentage` is recomputed as `6 / 21 * 100 = 28.6%`

#### Scenario: Insults-only mode — no folding

- GIVEN a session with only the `insults` sensor (no `emotions`)
- WHEN the session ends
- THEN `_fold_insults_into_rage()` is NOT called
- AND `insult_count` appears raw in the CSV without affecting rage percentages

#### Scenario: Zero insults — no-op

- GIVEN `insult_count=0`
- WHEN `_fold_insults_into_rage()` is called
- THEN the summary dict is returned unchanged

### Requirement: HUD Counter Pill

The `_draw_mic_indicator` method in `camera.py` SHALL be extended with a second pill `INSULTOS x{n}` when an `insult_detector` is attached. The pill MUST show the live counter only — no volume bar, no transcript text. It MUST follow the same placement and styling as the scream counter pill.

#### Scenario: HUD shows insult counter

- GIVEN the detector is running and has matched 5 insults
- WHEN the frame is rendered
- THEN the HUD MUST display `INSULTOS x5` as a text pill
- AND no recognized words appear anywhere on the frame

#### Scenario: No insult detector — no pill

- GIVEN `insult_detector` is `None` (not attached to the camera)
- WHEN the frame is rendered
- THEN the `INSULTOS` pill MUST NOT appear

#### Scenario: Zero insults — pill still visible

- GIVEN the detector is running but has matched 0 insults
- WHEN the frame is rendered
- THEN the `INSULTOS x0` pill is shown (confirms the sensor is active)

### Requirement: Dashboard API — Insult Fields

The dashboard API (`/api/data`) MUST expose `insult_count` and `insult_peak_count` in the per-session object, and `total_insults` in the `global_stats` object. The `loudest_game` calculation SHALL remain based on scream count (not insult count). An `insults_leaderboard` entry SHALL exist as a separate tile.

#### Scenario: API returns insult data

- GIVEN a sessions.csv has rows with `insult_count=3` and `insult_peak_count=1`
- WHEN the client fetches `/api/data`
- THEN the JSON session object MUST contain `"insult_count": 3` and `"insult_peak_count": 1`
- AND `global_stats.total_insults` MUST be the sum across all sessions

#### Scenario: Old CSV values — default to 0

- GIVEN a session row that has no `insult_count` column (pre-migration)
- WHEN the API loads it
- THEN `.get("insult_count", 0)` MUST return `0`

### Requirement: Dashboard UI — Insult Leaderboard Tile

The `dashboard.html` MUST render an Insult Leaderboard tile that mirrors the Scream Leaderboard layout: ranked games by total insult count, with a heat chip showing the per-game average. An insult heat chip SHALL also appear in the game details card.

#### Scenario: Insult leaderboard renders

- GIVEN there are sessions with `insult_count` data across multiple games
- WHEN the dashboard HTML renders
- THEN a tile "INSULTOS POR JUEGO" (or equivalent) MUST show games ranked by total insult count
- AND the top entry has a highlighted badge

#### Scenario: No insult data — leaderboard empty

- GIVEN no sessions have `insult_count > 0` or the column was just added
- WHEN the dashboard renders
- THEN the insult leaderboard SHALL show "Sin datos de insultos" (or equivalent)

### Requirement: Launcher Sensor Toggle

The launcher MUST add an `insult_var` checkbox labeled `INSULTOS (beta)` in the sensor panel, following the exact layout and spacing as the `scream_var` checkbox. When enabled, the subprocess command MUST include `insults` in the `--sensors` list.

#### Scenario: Insult sensor toggle

- GIVEN the launcher GUI is open
- WHEN the user checks `INSULTOS (beta)`
- THEN the sensor list passed to the session subprocess includes `"insults"`
- AND the detector is created and started alongside the scream monitor

#### Scenario: Both insults and scream sensors

- GIVEN the user checks both `GRITOS` and `INSULTOS (beta)`
- WHEN the session starts
- THEN `--sensors emotions insults scream` is passed to the subprocess
- AND both `AudioMonitor` and `InsultDetector` are created independently

### Requirement: CLI `--sensors` Includes Insults

The `main.py` argument parser SHALL include `"insults"` in the `choices` list for `--sensors`.

#### Scenario: CLI starts insults sensor

- GIVEN `main.py --sensors insults` is run
- WHEN `session_runner.run_session()` receives `insults` in the sensor set
- THEN an `InsultDetector` is created and started
- AND the session collects insult data