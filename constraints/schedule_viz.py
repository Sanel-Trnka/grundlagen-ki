"""
schedule_viz.py
───────────────
Grafische Belegungspläne für CSP-Lösungen (python-constraint & OR-Tools).

Füge diese Datei in denselben Ordner wie dein Notebook und importiere:

    from schedule_viz import show_schedule, embed_schedule_md, display_all_schedules

Kompatibel mit beiden Solver-Lösungsformaten:
    solution = {"G1_A": ("Mon", 1, "L1", "K1"), ...}
"""

from __future__ import annotations

import base64
import io

import matplotlib
matplotlib.use("Agg")          # kein GUI-Fenster – sicher in Notebooks
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

try:
    from IPython.display import display, Markdown
except ImportError:
    pass  # Außerhalb von Jupyter-Umgebungen nicht benötigt

# ── Konstanten ────────────────────────────────────────────────────────────────
_DAY_ORDER = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
_DAY_LABELS = {
    "Mon": "Mon", "Tue": "Tue", "Wed": "Wed",
    "Thu": "Thu", "Fri": "Fri",
}
_TIMESLOT_LABELS = {
    1: "08:00–10:00",
    2: "10:30–12:30",
    3: "13:00–14:30",
    4: "15:00–17:00",
}
_TASK_LABELS = {"A": "A", "B": "B", "C": "C"}

# Pastellfarben (Hintergrund) + passende Textfarben pro Gruppe
_GROUP_BG = [
    "#fff9c4",  # gelb
    "#c8e6c9",  # grün
    "#bbdefb",  # blau
    "#f8bbd0",  # rosa
    "#b2ebf2",  # türkis
    "#e1bee7",  # lila
    "#ffccbc",  # orange
    "#d7ccc8",  # braun
    "#f0f4c3",  # limette
    "#cfd8dc",  # blaugrau
]
_GROUP_FG = [
    "#f57f17",  # gelb  → dunkelorange
    "#1b5e20",  # grün  → dunkelgrün
    "#0d47a1",  # blau  → dunkelblau
    "#b71c1c",  # rosa  → dunkelrot
    "#006064",  # türkis → dunkeltürkis
    "#4a148c",  # lila  → dunkellila
    "#bf360c",  # orange → dunkelorange
    "#3e2723",  # braun → dunkelbraun
    "#558b2f",  # limette → dunkelgrün
    "#37474f",  # blaugrau → dunkel
]

# Farben der Tabellenstruktur
_HEADER_BG = "#2d3250"   # dunkles Blau-Lila für Kopfzeile
_HEADER_FG = "#ffffff"
_ROOM_BG   = "#1e2235"   # noch dunkler für Raum-Labels
_ROOM_FG   = "#ffffff"
_TIME_BG   = "#3d4370"   # mittel für Zeit-Labels
_TIME_FG   = "#e8eaf6"
_EMPTY_BG  = "#f5f6fa"   # fast weiß für leere Zellen
_GRID_CLR  = "#c5c8e0"   # Gitternetzlinien


# ── Interne Hilfsfunktionen ───────────────────────────────────────────────────

def _group_color_map(solution: dict) -> dict[str, tuple[str, str]]:
    """Gibt für jede Gruppe ein (bg_color, fg_color)-Tupel zurück."""
    groups = sorted({var.split("_")[0] for var in solution})
    return {
        g: (_GROUP_BG[i % len(_GROUP_BG)], _GROUP_FG[i % len(_GROUP_FG)])
        for i, g in enumerate(groups)
    }


def _parse_timeslots(config: dict) -> list[int]:
    ts = config.get("timeslots", [])
    return sorted(int(t) for t in (ts.keys() if isinstance(ts, dict) else ts))


def _rect(ax, x, y, w, h, fc, ec=None, lw=0.8, zorder=1, radius=0.0):
    """Zeichnet ein (optional abgerundetes) Rechteck."""
    if radius > 0:
        patch = FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad={radius}",
            facecolor=fc, edgecolor=ec or fc, linewidth=lw, zorder=zorder,
        )
    else:
        patch = mpatches.Rectangle(
            (x, y), w, h,
            facecolor=fc, edgecolor=ec or fc, linewidth=lw, zorder=zorder,
        )
    ax.add_patch(patch)


def _text(ax, x, y, s, size=8, color="#222", ha="center", va="center",
          weight="normal", rotation=0, zorder=5):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va,
            fontweight=weight, rotation=rotation, zorder=zorder,
            fontfamily="DejaVu Sans")


# ── Kernfunktion ──────────────────────────────────────────────────────────────

def plot_schedule(
    solution: dict,
    config: dict,
    title: str = "Gesamter Raum- und Zeitplan",
    save_path: str | None = None,
    figsize: tuple | None = None,
    dpi: int = 150,
    embed_base64: bool = False,
) -> tuple:
    """Erstellt einen tabellenartigen Belegungsplan als Matplotlib-Abbildung.

    Layout: Räume als Zeilengruppen (links), Zeitslots als Unterzeilen,
    Tage als Spalten. Pastellfarben nach Gruppe, dunkle Kopfzeile.

    Parameters
    ----------
    solution : dict
        Lösung im Format ``{"G1_A": ("Mon", 1, "L1", "K1"), ...}``.
        Kompatibel mit python-constraint- **und** OR-Tools-Lösungen.
    config : dict
        Konfigurationsdict aus ``load_config`` / ``analyze_and_display``.
    title : str
        Diagrammtitel über der Tabelle.
    save_path : str | None
        Wenn angegeben, wird die Grafik als PNG gespeichert.
    figsize : tuple | None
        ``(Breite, Höhe)`` in Zoll – wird automatisch ermittelt, wenn None.
    dpi : int
        Auflösung (Standard 150; 120 reicht für Markdown-Einbettung).
    embed_base64 : bool
        Wenn True, wird zusätzlich ein Markdown-``<img>``-Tag zurückgegeben.

    Returns
    -------
    fig : matplotlib.figure.Figure
    md_tag : str | None
        Nur wenn ``embed_base64=True``: fertiger Markdown-Image-String.
    """
    if solution is None:
        raise ValueError("solution ist None – keine Lösung zum Visualisieren.")

    days      = sorted(config.get("days", []),  key=lambda d: _DAY_ORDER.get(d, 99))
    rooms     = sorted(config.get("rooms", []))
    timeslots = _parse_timeslots(config)

    n_d  = len(days)
    n_r  = len(rooms)
    n_ts = len(timeslots)

    # ── Zelldimensionen ──────────────────────────────────────────────────────
    CW  = 2.8   # Breite einer Tag-Spalte
    CH  = 1.0   # Höhe einer Zeitslot-Zeile
    RLW = 0.65  # Breite der Raum-Label-Spalte
    TLW = 1.55  # Breite der Zeit-Label-Spalte
    HH  = 0.60  # Höhe der Header-Zeile
    SEP = 0.07  # Trennstreifen zwischen Räumen

    total_w = RLW + TLW + n_d * CW
    total_h = HH + n_r * (n_ts * CH) + (n_r - 1) * SEP

    if figsize is None:
        scale = 0.82
        figsize = (total_w * scale, total_h * scale)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_xlim(0, total_w)
    ax.set_ylim(0, total_h)
    ax.invert_yaxis()
    ax.axis("off")
    fig.patch.set_facecolor("#ffffff")

    color_map   = _group_color_map(solution)
    cell_lookup = {}
    for var, (day, ts, room, commission) in solution.items():
        group, task = var.split("_", 1)
        cell_lookup[(day, int(ts), room)] = (group, task, commission)

    # ── Kopfzeile ────────────────────────────────────────────────────────────
    _rect(ax, 0, 0, RLW + TLW, HH, fc=_HEADER_BG)
    _text(ax, (RLW + TLW) / 2, HH / 2, "Raum  ·  Zeit",
          size=8.0, color=_HEADER_FG, weight="bold")

    for ci, day in enumerate(days):
        x0 = RLW + TLW + ci * CW
        _rect(ax, x0, 0, CW, HH, fc=_HEADER_BG, ec=_ROOM_BG, lw=1.0)
        _text(ax, x0 + CW / 2, HH / 2, _DAY_LABELS.get(day, day),
              size=10, color=_HEADER_FG, weight="bold")

    # ── Raum-Gruppen ─────────────────────────────────────────────────────────
    for ri, room in enumerate(rooms):
        y_top = HH + ri * (n_ts * CH + SEP)

        # Trennstreifen zwischen Räumen
        if ri > 0:
            _rect(ax, 0, y_top - SEP, total_w, SEP, fc=_ROOM_BG)

        # Raum-Label (links, über alle Zeitslots)
        _rect(ax, 0, y_top, RLW, n_ts * CH, fc=_ROOM_BG, ec=_ROOM_BG, lw=0)
        _text(ax, RLW / 2, y_top + n_ts * CH / 2, room,
              size=10, color=_ROOM_FG, weight="bold")

        for ti, ts in enumerate(timeslots):
            y = y_top + ti * CH

            # Zeit-Label
            _rect(ax, RLW, y, TLW, CH, fc=_TIME_BG, ec=_ROOM_BG, lw=0.4)
            _text(ax, RLW + TLW / 2, y + CH / 2,
                  _TIMESLOT_LABELS.get(ts, str(ts)),
                  size=7.2, color=_TIME_FG)

            # Tag-Zellen
            for ci, day in enumerate(days):
                x0  = RLW + TLW + ci * CW
                key = (day, ts, room)

                if key in cell_lookup:
                    group, task, commission = cell_lookup[key]
                    bg, fg = color_map[group]

                    _rect(ax, x0 + 0.05, y + 0.05,
                          CW - 0.10, CH - 0.10,
                          fc=bg, ec=fg, lw=1.1, zorder=2, radius=0.06)
                    _text(ax, x0 + CW / 2, y + CH * 0.35,
                          f"{group}  –  {_TASK_LABELS.get(task, task)}",
                          size=8.2, color=fg, weight="bold", zorder=3)
                    _text(ax, x0 + CW / 2, y + CH * 0.68,
                          f"Komm: {commission}",
                          size=7.0, color=fg, zorder=3)
                else:
                    _rect(ax, x0, y, CW, CH,
                          fc=_EMPTY_BG, ec=_GRID_CLR, lw=0.5, zorder=1)

    # ── Äußerer Rahmen ───────────────────────────────────────────────────────
    _rect(ax, 0, 0, total_w, total_h,
          fc="none", ec=_ROOM_BG, lw=1.8, zorder=10)

    # ── Titel ────────────────────────────────────────────────────────────────
    fig.text(0.5, 1.012, title, ha="center", va="bottom",
             fontsize=11, fontweight="bold", color=_HEADER_BG,
             fontfamily="DejaVu Sans")

    # ── Legende ──────────────────────────────────────────────────────────────
    handles = [
        mpatches.Patch(facecolor=bg, edgecolor=fg, label=g, linewidth=1.2)
        for g, (bg, fg) in sorted(color_map.items())
    ]
    ax.legend(
        handles=handles,
        title="Gruppen", title_fontsize=8,
        fontsize=7.5, loc="upper left",
        bbox_to_anchor=(1.01, 0.0), borderaxespad=0,
        frameon=True, framealpha=0.96, edgecolor=_HEADER_BG,
    )

    plt.tight_layout(pad=0.3)

    if save_path:
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        print(f"Grafik gespeichert unter: {save_path}")

    if embed_base64:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                    facecolor="white")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        return fig, f"![{title}](data:image/png;base64,{b64})"

    return fig, None


# ── Komfort-Wrapper für Notebooks ─────────────────────────────────────────────

def show_schedule(
    solution: dict,
    config: dict,
    title: str = "Gesamter Raum- und Zeitplan",
    save_path: str | None = None,
    dpi: int = 130,
) -> None:
    """Zeigt den Belegungsplan direkt als Notebook-Ausgabe an (plt.show()).

    Verwendung in einer Code-Zelle::

        show_schedule(solution_bt,  config, title="python-constraint – ConfigA")
        show_schedule(solution_ort, config, title="OR-Tools CP-SAT – ConfigA")
    """
    fig, _ = plot_schedule(solution, config, title=title,
                           save_path=save_path, dpi=dpi)
    plt.show()
    plt.close(fig)


def embed_schedule_md(
    solution: dict,
    config: dict,
    title: str = "Gesamter Raum- und Zeitplan",
    save_path: str | None = None,
    dpi: int = 120,
) -> str:
    """Erzeugt einen Markdown-``<img>``-String zum Einbetten in Markdown-Zellen.

    Verwendung in einer Code-Zelle::

        from IPython.display import display, Markdown
        display(Markdown(embed_schedule_md(solution_bt, config, "ConfigA – python-constraint")))

    Parameters
    ----------
    solution  : Lösungs-Dict des Solvers.
    config    : Konfigurationsdict (direkt aus ``load_config``).
    title     : Titel über der Tabelle.
    save_path : Optionaler Pfad zum zusätzlichen Speichern als PNG.
    dpi       : Auflösung (120 reicht für Markdown-Einbettung).

    Returns
    -------
    str
        Markdown-String der Form ``![title](data:image/png;base64,...)``.
    """
    fig, md_tag = plot_schedule(
        solution, config, title=title,
        save_path=save_path, dpi=dpi, embed_base64=True,
    )
    plt.close(fig)
    return md_tag


def display_all_schedules(
    solver_results: list[tuple[dict, dict, str]],
    dpi: int = 120,
) -> None:
    """Zeigt mehrere Belegungspläne nacheinander als Markdown-Grafiken an.

    Verwendung in Abschnitt 7::

        from schedule_viz import display_all_schedules

        display_all_schedules([
            (solution_bt_A,  configA, "ConfigA – python-constraint"),
            (solution_ort_A, configA, "ConfigA – OR-Tools CP-SAT"),
            (solution_bt_B,  configB, "ConfigB – python-constraint"),
            (solution_ort_B, configB, "ConfigB – OR-Tools CP-SAT"),
            (solution_bt_C,  configC, "ConfigC – python-constraint"),
            (solution_ort_C, configC, "ConfigC – OR-Tools CP-SAT"),
        ])

    Wenn ein Solver ``None`` zurückgibt (z. B. ConfigC), wird automatisch
    ein Hinweis angezeigt statt einer leeren Grafik.
    """
    for solution, config, title in solver_results:
        display(Markdown(f"### {title}"))
        if solution is None:
            display(Markdown(
                "*Keine Lösung gefunden – Grafik wird übersprungen.*"
            ))
        else:
            display(Markdown(embed_schedule_md(solution, config, title, dpi=dpi)))