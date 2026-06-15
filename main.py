"""Console entry point for the qualifying lap-time exercise."""

from __future__ import annotations

import argparse
import sys
import json

# Analysis logics
from qualifying_analyzer import (
    DatasetError,
    analyse_driver,
    build_classification,
    format_driver_result,
    format_lap_time,
    list_drivers,
    load_laps,
)

# Words a user can type to leave the interactive prompt.
EXIT_WORDS = {"exit", "quit", "q"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show a driver's best valid Q1/Q2/Q3 lap times and final qualifying position."
    )
    parser.add_argument(
        "--file", "-f",
        default="data/session_laptimes.json",
        help="Path to session_laptimes.json. Default: data/session_laptimes.json",
    )
    parser.add_argument(
        "--driver", "-d",
        help="Three-letter driver code, e.g. HUL or BOR. If omitted, you enter an "
             "interactive prompt and can look up several drivers in a row.",
    )
    parser.add_argument(
        "--list-drivers", action="store_true",
        help="List available driver codes and exit.",
    )
    parser.add_argument(
        "--classification", action="store_true",
        help="Print the full qualifying classification and exit.",
    )
    return parser.parse_args()


def run_interactive(laps) -> int:
    """Prompt for driver codes in a loop until the user chooses to quit.

    An unknown or malformed code is reported and the prompt simply asks again --
    it is not a fatal error. The loop ends on an empty line, an exit word, or
    end-of-input (Ctrl-D / Ctrl-C).
    """
    print("Available drivers:")
    print(", ".join(list_drivers(laps)))
    print('\nEnter a driver code (e.g. HUL, BOR). Press Enter on a blank line or type "exit" to quit.')

    while True:
        try:
            raw = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print()  # tidy newline after Ctrl-D / Ctrl-C
            return 0

        code = raw.strip()
        if not code or code.lower() in EXIT_WORDS:
            return 0

        try:
            result = analyse_driver(laps, code)
        except ValueError as exc:
            # Wrong/malformed code: show why, then loop and let them try again.
            print(f"Error: {exc}")
            continue

        print()
        print(format_driver_result(result))


def main() -> int:
    args = parse_args()

    try:
        laps = load_laps(args.file)
    except DatasetError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Temporary for checking
    # with open(args.file, "r", encoding="utf-8") as f:
    #     raw = json.load(f)

    # for column, values in raw.items():
    #     print(f"{column}: {len(values)} values")

    # return 0


    # with open("data/session_laptimes.json", "r", encoding="utf-8") as f:
    #     data = json.load(f)

    # for field in ["pos", "iacc"]:
    #     values = data.get(field)

    #     print(f"\n{field}:")
    #     if values is None:
    #         print("Field not found")
    #     else:
    #         print("First 20 values:", values[:20])
    #         print("Unique values:", sorted(set(values)))

    # if args.classification:
    #     print("Final qualifying classification")
    #     for entry in build_classification(laps):
    #         print(
    #             f"P{entry['position']:>2}  {entry['driver']:<3}  "
    #             f"{format_lap_time(entry['time_seconds'])}  "
    #             f"({entry['session']})"
    #         )
    #     return 0

    # Explicit --driver is a one-shot lookup (handy for scripting/piping).
    if args.driver:
        try:
            result = analyse_driver(laps, args.driver)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(format_driver_result(result))
        return 0

    # No driver given: drop into the interactive retry loop.
    return run_interactive(laps)


if __name__ == "__main__":
    raise SystemExit(main())
