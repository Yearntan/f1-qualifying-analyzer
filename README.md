# Australian GP Qualifying Lap-Time Exercise

This is a small Python console application for the Audi Revolut F1 Team Digital Solutions take-home exercise. It reads the Tracing Insights Australian Grand Prix qualifying `session_laptimes.json` file, asks for a driver code, and prints:

1. the selected driver's best valid lap time in Q1, Q2 and Q3; and
2. the driver's final classified qualifying position derived from the dataset.

## Language and framework choice

I chose Python because it is quick to run, easy for an interviewer to inspect, and well suited to a small data-processing task. I kept the implementation dependency-light: the application itself uses only the Python standard library. `pytest` is only needed if you want to run the automated tests.

## Project structure

```text
.
├── main.py                          # Console entry point (CLI only)
├── qualifying_analyzer.py           # Core parsing, validation and analysis logic
├── test_qualifying_analyzer.py      # Automated tests (pytest)
├── data/
│   └── session_laptimes.json        # Dataset used by the app
├── THIRD_PARTY_NOTICES.md           # Dataset attribution
└── README.md
```

## Setup

Python 3.10+ is recommended.

No runtime dependencies are required:

```bash
python main.py --help
```

To run the tests, install `pytest`:

```bash
python -m pip install pytest
python -m pytest
```

## Running the solution

From the project root:

```bash
python main.py --file data/session_laptimes.json --driver HUL
```

Example output:

```text
Driver: HUL

Best valid laps:
  Q1: 1:21.024 / 81.024s (lap 8)
  Q2: 1:20.303 / 80.303s (lap 15)
  Q3: N/A

Final classified qualifying position: P11 (classified on Q2: 1:20.303)
```

You can also run it interactively. With no `--driver`, the app enters a prompt
loop so you can look up several drivers in a row. An unknown or malformed code is
reported and you are asked again (it does not quit). Press Enter on a blank line,
type `exit`/`quit`/`q`, or press Ctrl-D to leave.

```bash
python main.py --file data/session_laptimes.json
```

```text
Available drivers:
ALB, ALO, ANT, BEA, BOR, ...

Enter a driver code (e.g. HUL, BOR). Press Enter on a blank line or type "exit" to quit.

> zzz
Error: Unknown driver code 'ZZZ'. Available drivers: ALB, ALO, ...

> hul
Driver: HUL
...

> exit
```

(Passing `--driver HUL` instead does a single lookup and exits, which is convenient
for scripting.)

List available driver codes:

```bash
python main.py --list-drivers
```

Print the whole classification:

```bash
python main.py --classification
```

## Approach and architecture

The code is split into two layers:

- `qualifying_analyzer.py` contains all data loading, validation, parsing, lap filtering and classification logic.
- `main.py` handles only command-line arguments, user input and presentation.

This separation keeps the business logic testable without depending on console input/output.

The Tracing Insights lap-time JSON is column-oriented: each field maps to a list of values. The loader validates that all column lengths match, then normalises the data into `Lap` dataclass objects. The same loader also accepts row-oriented JSON, which makes the logic easier to test with small fixtures.

## Valid lap handling

For the per-session best laps, a lap is treated as valid when:

- it has a real, finite, **positive** numeric lap time; and
- the lap has not been deleted by the stewards (`del` is false).

Null values such as `None`, the string `"None"`, malformed or non-positive numeric values, and deleted laps are all ignored for best-lap calculations.

I did not reject laps solely because `iacc` is false. The field reference says `iacc` concerns timing-data synchronisation, while lap and sector times are considered accurate if they exist. For a time-boxed exercise, excluding deleted or missing lap times is the clearer and safer interpretation of "valid lap".

## Final classification

The `pos` field is not populated for qualifying sessions, so I reconstruct the final classified order using the standard FIA knock-out logic, expressed purely in terms of what the dataset shows:

1. Each driver is anchored to the **furthest session they took part in** (Q3 ahead of Q2 ahead of Q1). Participation means appearing in the session at all, not necessarily setting a valid time.
2. Within that session, drivers are ordered by their **best valid lap time set in that session** (fastest first).
3. The groups are concatenated Q3 → Q2 → Q1 and numbered from P1.

I deliberately do **not** assume the usual 15/10 elimination cut-offs, because they do not hold for this dataset (Q2 has 16 drivers and Q3 has 9, not 15 and 10). Deriving the groups from actual participation handles that automatically.

This also produces the correct, sometimes counter-intuitive result that a driver who reached Q3 is classified ahead of every Q2 driver even when their Q3 time is slower. For example, LIN's best Q3 lap (1:21.247) is slower than their own Q2 lap and slower than several Q2 drivers, yet LIN is classified P9 — ahead of the entire Q2 group — because progressing to Q3 always outranks being knocked out in Q2.

### Why not use the `pb` (personal-best) field?

The dataset's `pb` flag marks a driver's single official personal best across the *whole* session, not their best lap *per qualifying segment*. Ranking everyone by their `pb`/fastest lap would order drivers by raw pace rather than by knock-out classification, which gives the wrong result whenever a driver's quickest lap was set in an earlier session than the one they were eliminated in (again, LIN is the clear example). The furthest-session method is the one that matches the official timing sheet.

## Error handling

The application handles:

- missing files;
- invalid JSON;
- unexpected JSON shapes;
- inconsistent column lengths;
- missing required fields;
- invalid driver input;
- unknown driver codes;
- null, malformed, or non-positive lap times.

Errors are reported clearly on the console with a non-zero exit code.

## Trade-offs

This is intentionally a small console app rather than a web or desktop app. Given the suggested 90-minute time box, I prioritised clarity, testability, and defensible assumptions over UI complexity.

The loader is intentionally strict: it rejects ragged column lengths and unrecognised session values rather than guessing, so a structurally broken file fails fast with a clear message instead of producing silently-wrong results. A more lenient alternative would be to load whatever rows are well-formed and skip the rest; I judged fail-fast to be safer for a results-classification task.

## Use of AI

I used AI assistance to help structure the solution, identify edge cases, and draft the README. I reviewed and adjusted the implementation decisions myself, especially the definition of valid laps and the FIA furthest-session classification logic. I can explain the parsing, filtering, classification and error-handling logic in the interview.

## What I would do next with more time

- Add a small table-based output formatter for multiple selected drivers.
- Add optional CSV/JSON export.
- Add in-app data visualisation.
- Cross-check the derived bests against the `pb` flag as a data-quality report.
- Explicitly classify and optionally exclude in-/out-laps using the `pin`/`pout` fields.
- Add type checking with `mypy`, linting with `ruff`, and a CI workflow.
