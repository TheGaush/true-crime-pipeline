"""Spoken lines for the offline 90-second episode. No network."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    start: float
    text: str
    scene: str


# Starts are placed so each line finishes before the next scene, with a pause between lines.
LINES: tuple[Line, ...] = (
    Line(0.6, "An illustrative case file.", "title"),
    Line(3.5, "The porch at ten fourteen, Mercer County.", "title"),
    Line(7.6, "No one here is a real person.", "title"),
    Line(12.8, "Just after ten fourteen at night, a silhouette crossed the porch.", "porch"),
    Line(18.4, "The lamp over the door was lit.", "porch"),
    Line(21.5, "The figure did not knock, did not speak, and did not look back.", "porch"),
    Line(27.2, "It walked the length of the boards and was gone.", "porch"),
    Line(34.6, "The only record is a short clip from the porch camera.", "evidence"),
    Line(39.2, "First you hear the boards take the weight.", "evidence"),
    Line(42.6, "Then a pause. Then the night is quiet again.", "evidence"),
    Line(46.8, "There is no second angle.", "evidence"),
    Line(52.6, "A witness wrote that a figure passed the lamp and did not stop.", "affidavit"),
    Line(57.3, "The statement sits in the file with the name covered.", "affidavit"),
    Line(61.4, "What remains is the path, the hour, and a door that stayed shut.", "affidavit"),
    Line(70.6, "The last image is a frame from a public file.", "foia"),
    Line(75.0, "The face stays hidden on purpose.", "foia"),
    Line(78.8, "This is a synthetic reconstruction, labeled so it cannot be mistaken for a real person.", "foia"),
)


def script_text() -> str:
    return " ".join(line.text for line in LINES)


def active_line(t: float) -> str:
    current = LINES[0].text
    for line in LINES:
        if t + 1e-6 >= line.start:
            current = line.text
        else:
            break
    return current


def caption_lines(t: float, width: int = 52) -> list[str]:
    words = active_line(t).upper().split()
    rows: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if len(trial) <= width:
            current = trial
            continue
        if current:
            rows.append(current)
        current = word
    if current:
        rows.append(current)
    return rows[:3]
