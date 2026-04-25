from __future__ import annotations

from pathlib import Path
import json
import ast
from collections import defaultdict

import pandas as pd
from IPython.display import display, Markdown

pd.set_option("display.max_colwidth", None)

DAY_ORDER = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
TIMESLOT_LABELS = {
    1: "08:00–10:00",
    2: "10:30–12:30",
    3: "13:00–14:30",
    4: "15:00–17:00",
}
DEFAULT_COLORS = [
    "#fde2e4", "#e2f0cb", "#cddafd", "#fff1c1", "#d9f0ff",
    "#f6d8ff", "#dff7e2", "#ffd9c7", "#ede7f6", "#e0f7fa",
]


def resolve_config_path(config_path: str | Path = "config.json") -> Path:
    path = Path(config_path)
    if path.exists():
        return path
    json_candidates = sorted(Path(".").glob("*.json"))
    if json_candidates:
        return json_candidates[0]
    raise FileNotFoundError(
        "Keine Konfigurationsdatei gefunden. Lege z. B. eine 'config.json' im Arbeitsordner ab."
    )


def load_config(path: str | Path):
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw), "json"
    except Exception as json_error:
        try:
            return ast.literal_eval(raw), "python_literal"
        except Exception as literal_error:
            raise ValueError(
                "Die Datei konnte weder als JSON noch als Python-Literal gelesen werden.\n"
                f"JSON-Fehler: {json_error}\n"
                f"Literal-Fehler: {literal_error}"
            )


def normalize_availability_slot(slot):
    if isinstance(slot, (list, tuple)) and len(slot) == 2:
        day, timeslot = slot
        return str(day), int(timeslot)
    raise ValueError(f"Ungültiges Verfügbarkeitsformat: {slot}")


def get_timeslot_text(ts):
    try:
        ts_int = int(ts)
        return f"{ts_int} ({TIMESLOT_LABELS.get(ts_int, 'keine Beschreibung')})"
    except Exception:
        return str(ts)


def build_competence_table(commissions: dict) -> pd.DataFrame:
    all_topics = sorted({topic for topics in commissions.values() for topic in topics})
    competence_rows = []
    for commission, topics in sorted(commissions.items()):
        row = {"Kommission": commission, "Themen": ", ".join(topics)}
        for topic in all_topics:
            row[topic] = "✓" if topic in topics else ""
        competence_rows.append(row)
    competence_df = pd.DataFrame(competence_rows)
    ordered_cols = ["Kommission", "Themen"] + all_topics
    return competence_df[ordered_cols]


def build_commission_colors(commissions: dict) -> dict:
    commission_names = sorted(commissions.keys())
    return {
        commission: DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
        for i, commission in enumerate(commission_names)
    }


def build_legend_table(commission_colors: dict) -> pd.io.formats.style.Styler:
    legend_df = pd.DataFrame(
        [{"Kommission": c, "Farbe": ""} for c in sorted(commission_colors.keys())]
    )

    def style_farbe_column(col):
        if col.name != "Farbe":
            return [""] * len(col)
        return [
            f"background-color: {commission_colors[commission]};"
            for commission in legend_df["Kommission"]
        ]

    return (
        legend_df.style
        .hide(axis="index")
        .apply(style_farbe_column, subset=["Farbe"])
        .set_properties(subset=["Kommission"], **{"font-weight": "bold"})
    )


def build_schedule_table(config: dict) -> pd.DataFrame:
    availability = config.get("availability", {})
    days = config.get("days", [])
    timeslots = config.get("timeslots", [])

    availability_map = defaultdict(list)
    for commission, slots in availability.items():
        for slot in slots:
            day, ts = normalize_availability_slot(slot)
            availability_map[(day, ts)].append(commission)

    sorted_days = sorted(days, key=lambda d: DAY_ORDER.get(d, 999))
    sorted_timeslots = sorted(
        [int(ts) for ts in (timeslots.keys() if isinstance(timeslots, dict) else timeslots)]
    )

    plan_index = [f"{ts} ({TIMESLOT_LABELS.get(ts, '')})" for ts in sorted_timeslots]
    plan_data = {}
    for day in sorted_days:
        col_values = []
        for ts in sorted_timeslots:
            comms = sorted(availability_map.get((day, ts), []))
            col_values.append(", ".join(comms) if comms else "—")
        plan_data[day] = col_values

    schedule_df = pd.DataFrame(plan_data, index=plan_index)
    schedule_df.index.name = "Zeitslot"
    return schedule_df


def style_schedule(df: pd.DataFrame, commission_colors: dict) -> pd.io.formats.style.Styler:
    def style_cell(value):
        if value == "—":
            return "background-color: #f5f5f5; color: #666;"

        comms = [c.strip() for c in str(value).split(",") if c.strip()]
        colors = [commission_colors[c] for c in comms if c in commission_colors]

        if not colors:
            return ""
        if len(colors) == 1:
            return f"background-color: {colors[0]};"

        step = 100 / len(colors)
        segments = []
        current = 0
        for color in colors:
            next_pos = current + step
            segments.append(f"{color} {current:.2f}% {next_pos:.2f}%")
            current = next_pos
        gradient = ", ".join(segments)
        return f"background: linear-gradient(90deg, {gradient});"

    return (
        df.style
        .map(style_cell)
        .set_properties(**{
            "text-align": "center",
            "white-space": "pre-wrap",
            "font-weight": "bold",
        })
        .set_table_styles([
            {"selector": "th", "props": [("text-align", "center")]},
            {"selector": "td", "props": [("min-width", "180px"), ("height", "42px")]},
        ])
    )


def analyze_and_display(config_path: str | Path = "config.json") -> dict:
    resolved_path = resolve_config_path(config_path)
    config, load_mode = load_config(resolved_path)

    groups = config.get("groups", [])
    days = config.get("days", [])
    timeslots = config.get("timeslots", [])
    rooms = config.get("rooms", [])
    commissions = config.get("commissions", {})
    availability = config.get("availability", {})

    display(Markdown("# CSP-Konfiguration"))
    print(f"Verwendete Datei: {resolved_path.resolve()}")
    print(f"Lademodus: {load_mode}")

    display(Markdown("## Übersicht"))
    print("Gruppen:")
    print("  " + ", ".join(groups) if groups else "  -")

    print("Tage:")
    print("  " + ", ".join(days) if days else "  -")

    print("Zeitslots:")
    if isinstance(timeslots, dict):
        for k, v in sorted(timeslots.items(), key=lambda x: int(x[0])):
            print(f"  {k}: {v}")
    else:
        for ts in timeslots:
            print(f"  {get_timeslot_text(ts)}")

    print("Räume:")
    print("  " + ", ".join(rooms) if rooms else "  -")

    print("Anzahl Kommissionen:")
    print(f"  {len(commissions)}")

    print("Anzahl Verfügbarkeits-Einträge:")
    print(f"  {sum(len(v) for v in availability.values())}")

    display(Markdown("## Kompetenzen der Kommissionen"))
    competence_df = build_competence_table(commissions)
    display(competence_df)

    display(Markdown("## Legende"))
    commission_colors = build_commission_colors(commissions)
    display(build_legend_table(commission_colors))

    display(Markdown("## Wochenplan der Verfügbarkeiten"))
    schedule_df = build_schedule_table(config)
    display(style_schedule(schedule_df, commission_colors))

    return config