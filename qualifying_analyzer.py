"""Core analysis logic for the Australian GP qualifying lap-time exercise.

The Tracing Insights lap-time JSON is column-oriented: each key maps to a list of
values. This module also accepts a list of row dictionaries so the logic is easy
to test with small fixtures.
"""

# Make type hints cleaner
from __future__ import annotations

# Simple classes to store data
from dataclasses import dataclass
import json
import math
from pathlib import Path
# Hint Helpers
from typing import Any, Iterable

SESSIONS = ("Q1", "Q2", "Q3")
# Furthest-session-reached order, latest first. A driver's final classification
# is anchored to the latest qualifying session they took part in.
SESSION_PRECEDENCE = ("Q3", "Q2", "Q1")
# Required fields in json
REQUIRED_FIELDS = ("drv", "time", "qs")

# Error handling when dataset is bad
class DatasetError(Exception):
    """Raised when the input file cannot be read or has an unsupported shape."""

# Read-only lap data, Lap object & rule to decide whether lap is valid
@dataclass(frozen=True)
class Lap:
    driver: str
    session: str
    lap_number: int | None
    time_seconds: float | None
    deleted: bool

    @property
    def is_valid(self) -> bool:
        """A valid lap has a real, finite, positive time and was not deleted."""
        return (
            self.time_seconds is not None
            and math.isfinite(self.time_seconds)
            and self.time_seconds > 0
            and not self.deleted
        )

# Best valid lap for one session
@dataclass(frozen=True)
class SessionBest:
    session: str
    lap_time_seconds: float
    lap_number: int | None

# Final result for one driver
@dataclass(frozen=True)
class DriverResult:
    driver: str
    session_bests: dict[str, SessionBest | None]
    qualifying_position: int | None
    final_session: str | None
    classified_time_seconds: float | None

# Loads JSON file & converts to list of Lap object
def load_laps(path: str | Path) -> list[Lap]:
    """Load laps from a JSON file path and normalise them into Lap objects."""
    file_path = Path(path)
    try:
        with file_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError as exc:
        raise DatasetError(f"File not found: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetError(f"Invalid JSON in {file_path}: {exc}") from exc
    except OSError as exc:
        raise DatasetError(f"Could not read {file_path}: {exc}") from exc
    
    # Column to row 
    rows = _normalise_to_rows(raw)
    # Row to Lap object
    return [_row_to_lap(row, index=i) for i, row in enumerate(rows)]

# raw JSON to list of row dictionaries
def _normalise_to_rows(raw: Any) -> list[dict[str, Any]]:
    """Accept either column-oriented JSON or row-oriented JSON."""
    if isinstance(raw, list):
        if not all(isinstance(item, dict) for item in raw):
            raise DatasetError("Row-oriented JSON must be a list of objects.")
        return raw

    if not isinstance(raw, dict):
        raise DatasetError("JSON must be either an object of columns or a list of rows.")
    
    # Require drv, time & qs
    missing = [field for field in REQUIRED_FIELDS if field not in raw]
    if missing:
        raise DatasetError(f"Dataset is missing required field(s): {', '.join(missing)}")
    
    # Ensure all fields are lists
    lengths = {key: len(value) for key, value in raw.items() if isinstance(value, list)} #Create dic of column lengths
    if len(lengths) != len(raw):
        non_lists = [key for key, value in raw.items() if not isinstance(value, list)]
        raise DatasetError(f"All column values must be lists. Non-list field(s): {', '.join(non_lists)}")

    if not lengths:
        return []
    
    # All columns have same length
    expected = next(iter(lengths.values()))
    mismatched = {key: length for key, length in lengths.items() if length != expected}
    if mismatched:
        details = ", ".join(f"{key}={length}" for key, length in mismatched.items())
        raise DatasetError(f"Column lengths are inconsistent: expected {expected}; {details}")

    return [{key: raw[key][i] for key in raw} for i in range(expected)]

# Convert one raw row into clean Lap
def _row_to_lap(row: dict[str, Any], index: int) -> Lap:
    driver = _clean_string(row.get("drv")) # Remove messy values
    session = _clean_string(row.get("qs"))

    if not driver:
        raise DatasetError(f"Row {index} is missing driver code field 'drv'.")
    if session not in SESSIONS:
        raise DatasetError(f"Row {index} has unsupported qualifying session: {session!r}")

    return Lap(
        driver=driver.upper(),
        session=session,
        lap_number=_parse_int(row.get("lap")),
        time_seconds=_parse_float(row.get("time")),
        deleted=_parse_bool(row.get("del"), default=False),
    )

# Driver lists
def list_drivers(laps: Iterable[Lap]) -> list[str]:
    return sorted({lap.driver for lap in laps})


def analyse_driver(laps: Iterable[Lap], driver: str) -> DriverResult:
    """Return best valid Q1/Q2/Q3 laps and final qualifying position for a driver."""
    normalised_driver = _normalise_driver_input(driver)
    lap_list = list(laps)
    drivers = list_drivers(lap_list)

    # Unknown driver handler
    if normalised_driver not in drivers:
        raise ValueError(
            f"Unknown driver code '{normalised_driver}'. Available drivers: {', '.join(drivers)}"
        )
    
    # Best lap in each session
    session_bests = {
        session: _best_lap_for_session(lap_list, normalised_driver, session)
        for session in SESSIONS
    }

    position = None
    classified_time = None
    final_session = None
    for entry in build_classification(lap_list):
        if entry["driver"] == normalised_driver:
            position = entry["position"]
            classified_time = entry["time_seconds"]
            final_session = entry["session"]
            break

    return DriverResult(
        driver=normalised_driver,
        session_bests=session_bests,
        qualifying_position=position,
        final_session=final_session,
        classified_time_seconds=classified_time,
    )

# Lap obj -> Dictionaries list
def build_classification(laps: Iterable[Lap]) -> list[dict[str, Any]]:
    """Build the final classification using the FIA qualifying knock-out logic.

    The `pos` field is not populated during qualifying, so the order is
    reconstructed from the data:

      1. Each driver is anchored to the furthest session they took part in
         (Q3 ahead of Q2 ahead of Q1).
      2. Within that session, drivers are ordered by their best valid lap time
         set in that session (fastest first).
      3. The groups are concatenated Q3 -> Q2 -> Q1 and numbered from P1.

    This deliberately does NOT assume fixed 15/10 elimination cut-offs -- they do
    not hold for this dataset (Q2 has 16 drivers, Q3 has 9). Reconstructing the
    groups from actual participation handles that automatically. It also means a
    Q3 driver is always classified ahead of any Q2 driver even if the Q3 driver's
    best time is slower: progressing further always wins.
    """
    lap_list = list(laps)
    entries: list[tuple[str, float | None, str]] = []

    # Driver lists
    for driver in list_drivers(lap_list):
        driver_laps = [lap for lap in lap_list if lap.driver == driver]
        # Furthest sessions driver is in
        final_session = _furthest_session(driver_laps)
        if final_session is None:
            continue
        # Find fastest lap in final session
        best = _best_lap_for_session(lap_list, driver, final_session)
        # none if all laps were invalid
        best_time = best.lap_time_seconds if best is not None else None
        entries.append((final_session, best_time, driver))

    precedence = {session: i for i, session in enumerate(SESSION_PRECEDENCE)}
    entries.sort(
        key=lambda item: (
            precedence[item[0]],                       # later session ranks higher - final session
            item[1] is None,                           # no valid time sorts last in group 
            item[1] if item[1] is not None else 0.0,   # then fastest first -  best time
            item[2],                                   # alphabetical tie-break -driver - an assumption, alphabetical
        )
    )

    return [
        {
            "position": index + 1,
            "driver": driver,
            "session": session,
            "time_seconds": time_seconds,
        }
        for index, (session, time_seconds, driver) in enumerate(entries)
    ]


def _furthest_session(driver_laps: Iterable[Lap]) -> str | None:
    """The latest session a driver took part in (any lap), or None.

    Based on participation -- appearing in the session at all -- not on setting a
    valid time, so a driver who reached Q3 but had their only flying lap deleted
    is still grouped with Q3, at the back of it.
    """
    sessions = {lap.session for lap in driver_laps}
    for session in SESSION_PRECEDENCE:
        if session in sessions:
            return session
    return None


def _best_lap_for_session(laps: Iterable[Lap], driver: str, session: str) -> SessionBest | None:
    candidates = [
        lap
        for lap in laps
        if lap.driver == driver and lap.session == session and lap.is_valid
    ]
    if not candidates:
        return None

    best = min(candidates, key=lambda lap: lap.time_seconds)
    return SessionBest(
        session=session,
        lap_time_seconds=best.time_seconds,
        lap_number=best.lap_number,
    )


def format_lap_time(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    minutes = int(seconds // 60)
    remaining_seconds = seconds - (minutes * 60)
    return f"{minutes}:{remaining_seconds:06.3f}"


def format_driver_result(result: DriverResult) -> str:
    lines = [f"Driver: {result.driver}", ""]
    lines.append("Best valid laps:")
    for session in SESSIONS:
        best = result.session_bests[session]
        if best is None:
            lines.append(f"  {session}: N/A")
        else:
            lap_suffix = f" (lap {best.lap_number})" if best.lap_number is not None else ""
            lines.append(
                f"  {session}: {format_lap_time(best.lap_time_seconds)}"
                f" / {best.lap_time_seconds:.3f}s{lap_suffix}"
            )

    lines.append("")
    if result.qualifying_position is None:
        lines.append("Final classified qualifying position: N/A")
    else:
        lines.append(
            "Final classified qualifying position: "
            f"P{result.qualifying_position} "
            f"(classified on {result.final_session}: "
            f"{format_lap_time(result.classified_time_seconds)})"
        )
    return "\n".join(lines)


def _normalise_driver_input(driver: str) -> str:
    driver = (driver or "").strip().upper()
    if not driver:
        raise ValueError("Driver code cannot be empty.")
    if not driver.isalnum() or len(driver) > 4:
        raise ValueError("Driver code should be a short alphanumeric code, e.g. HUL or BOR.")
    return driver


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "" or stripped.lower() in {"none", "null"}:
            return None
        return stripped
    return str(value).strip()


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null", "nan"}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"true", "t", "1", "yes", "y"}:
            return True
        if cleaned in {"false", "f", "0", "no", "n", "none", "null", ""}:
            return False
    return default
