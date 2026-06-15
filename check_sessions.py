from qualifying_analyzer import load_laps

laps = load_laps("data/session_laptimes.json")

for session in ["Q1", "Q2", "Q3"]:
    drivers = sorted({lap.driver for lap in laps if lap.session == session})
    print(f"{session}: {len(drivers)} drivers")
    print(", ".join(drivers))
    print()