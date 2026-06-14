from pathlib import Path
import json

import pytest

from qualifying_analyzer import (
    DatasetError,
    analyse_driver,
    build_classification,
    format_lap_time,
    load_laps,
)

DATA_FILE = Path(__file__).resolve().parent / "data" / "session_laptimes.json"


def _write(tmp_path, payload):
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_format_lap_time():
    assert format_lap_time(80.303) == "1:20.303"
    assert format_lap_time(None) == "N/A"


def test_hul_result_from_provided_dataset():
    laps = load_laps(DATA_FILE)
    result = analyse_driver(laps, "hul")

    assert result.driver == "HUL"
    assert result.session_bests["Q1"].lap_time_seconds == pytest.approx(81.024)
    assert result.session_bests["Q2"].lap_time_seconds == pytest.approx(80.303)
    assert result.session_bests["Q3"] is None
    assert result.qualifying_position == 11
    assert result.final_session == "Q2"


def test_bor_result_from_provided_dataset():
    laps = load_laps(DATA_FILE)
    result = analyse_driver(laps, "BOR")

    assert result.session_bests["Q1"].lap_time_seconds == pytest.approx(80.495)
    assert result.session_bests["Q2"].lap_time_seconds == pytest.approx(80.221)
    assert result.session_bests["Q3"] is None
    assert result.qualifying_position == 10


def test_classification_uses_fia_knockout_on_real_data():
    laps = load_laps(DATA_FILE)
    classification = build_classification(laps)
    by_driver = {entry["driver"]: entry for entry in classification}

    # Fastest overall, classified P1 on a Q3 lap.
    assert classification[0]["driver"] == "RUS"
    assert classification[0]["session"] == "Q3"

    # VER only set a slow Q1 lap, so is classified last.
    assert classification[-1]["driver"] == "VER"
    assert by_driver["VER"]["session"] == "Q1"

    # LIN reached Q3 but set a slower time there than LAW (also Q3). Under the
    # knock-out, LAW is ahead of LIN, and BOTH are ahead of every Q2 driver -- so
    # LIN (slower Q3 time) still outranks BOR (a Q2 driver with a faster lap).
    assert by_driver["LIN"]["session"] == "Q3"
    assert by_driver["LAW"]["position"] < by_driver["LIN"]["position"]
    assert by_driver["LIN"]["position"] < by_driver["BOR"]["position"]
    assert by_driver["BOR"]["session"] == "Q2"


def test_q3_driver_outranks_faster_q2_driver(tmp_path):
    # AAA reaches Q3 with a slow 95.0; BBB only reaches Q2 with a fast 88.0.
    # FIA knock-out: AAA is classified ahead of BBB despite the slower time.
    fixture = {
        "drv":  ["AAA", "AAA", "AAA", "BBB", "BBB"],
        "qs":   ["Q1",  "Q2",  "Q3",  "Q1",  "Q2"],
        "lap":  [1,     2,     3,     1,     2],
        "time": [90.0,  89.0,  95.0,  90.5,  88.0],
        "del":  [False, False, False, False, False],
    }
    classification = build_classification(load_laps(_write(tmp_path, fixture)))
    assert [e["driver"] for e in classification] == ["AAA", "BBB"]
    assert classification[0]["time_seconds"] == pytest.approx(95.0)  # AAA's Q3 time


def test_driver_with_only_deleted_lap_in_final_session_still_grouped_there(tmp_path):
    # AAA's only Q2 lap is deleted -> no valid Q2 time, but they still reached Q2,
    # so they are grouped in Q2 and sorted behind BBB who set a valid Q2 lap.
    fixture = {
        "drv":  ["AAA", "AAA", "BBB", "BBB"],
        "qs":   ["Q1",  "Q2",  "Q1",  "Q2"],
        "lap":  [1,     2,     1,     2],
        "time": [90.0,  88.0,  90.5,  87.0],
        "del":  [False, True,  False, False],
    }
    classification = build_classification(load_laps(_write(tmp_path, fixture)))
    assert [e["driver"] for e in classification] == ["BBB", "AAA"]
    assert classification[1]["time_seconds"] is None  # AAA has no valid Q2 time


def test_deleted_lap_is_not_counted_for_session_best(tmp_path):
    fixture = {
        "drv":  ["ABC", "ABC"],
        "qs":   ["Q1",  "Q1"],
        "lap":  [1,     2],
        "time": [79.0,  80.0],
        "del":  [True,  False],
    }
    result = analyse_driver(load_laps(_write(tmp_path, fixture)), "ABC")
    assert result.session_bests["Q1"].lap_time_seconds == pytest.approx(80.0)


def test_none_string_and_nonpositive_times_are_invalid(tmp_path):
    fixture = {
        "drv":  ["ABC", "ABC", "ABC"],
        "qs":   ["Q1",  "Q1",  "Q1"],
        "lap":  [1,     2,     3],
        "time": ["None", 0.0,  81.5],   # null string and a zero are both invalid
        "del":  [False, False, False],
    }
    result = analyse_driver(load_laps(_write(tmp_path, fixture)), "ABC")
    assert result.session_bests["Q1"].lap_time_seconds == pytest.approx(81.5)


def test_inconsistent_column_lengths_raise_dataset_error(tmp_path):
    path = _write(tmp_path, {"drv": ["ABC"], "qs": ["Q1", "Q1"], "time": [80.0]})
    with pytest.raises(DatasetError):
        load_laps(path)


def test_unknown_driver_raises_value_error():
    laps = load_laps(DATA_FILE)
    with pytest.raises(ValueError):
        analyse_driver(laps, "ZZZ")


def test_interactive_loop_retries_after_bad_code(monkeypatch, capsys):
    """A wrong code should not exit: the loop reports it and keeps prompting."""
    import main as cli

    laps = load_laps(DATA_FILE)
    # First a bad code, then a good one, then quit.
    inputs = iter(["ZZZ", "HUL", "exit"])
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: next(inputs))

    rc = cli.run_interactive(laps)
    out = capsys.readouterr().out

    assert rc == 0
    assert "Unknown driver code 'ZZZ'" in out   # the bad code was reported...
    assert "Driver: HUL" in out                 # ...and the loop continued to answer HUL


def test_interactive_loop_exits_on_blank_line(monkeypatch, capsys):
    import main as cli

    laps = load_laps(DATA_FILE)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
    assert cli.run_interactive(laps) == 0
