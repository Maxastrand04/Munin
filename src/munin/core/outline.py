"""The Outline's JSON format: its schema, its samples, and the check every render runs first."""

import re
from dataclasses import dataclass
from typing import NamedTuple

from munin.core.errors import OutlineProblem
from munin.core.latex import BrokenLatex, calculation_problems, prose_problems
from munin.core.stamps import display_stamp, stamp_seconds


class _Part(NamedTuple):
    """One part in the parts table.

    `kind` says what the value holds. `text` and `prose` are strings, and only
    `prose` may hold control characters, such as newlines. `required` says the
    part must be non-blank. `math` says how the render checks its LaTeX:
    `prose` for math between `$...$`, `calculation` for LaTeX alone, or None
    for no check.
    """

    kind: str
    required: bool
    math: str | None = None


_TREE_PARTS = {
    "label": _Part("text", True),
    "explanation": _Part("prose", False, "prose"),
    "stamps": _Part("stamps", False),
    "slides": _Part("slides", False),
    "children": _Part("nodes", False),
}
_WORKED_PARTS = {
    "label": _Part("text", True),
    "stamps": _Part("stamps", False),
    "slides": _Part("slides", False),
    "task": _Part("text", True, "prose"),
    "steps": _Part("steps", False),
    "answer": _Part("text", False, "prose"),
}
_STEP_PARTS = {
    "calculation": _Part("text", True, "calculation"),
    "reason": _Part("text", False, "prose"),
}
# The parts table: every node type and its parts. The schema and the check are both built from it.
_PARTS: dict[str, dict[str, _Part]] = {
    "main-topic": _TREE_PARTS,
    "topic": _TREE_PARTS,
    "slide": _TREE_PARTS,
    "term": _TREE_PARTS,
    "example": _WORKED_PARTS,
    "exercise": _WORKED_PARTS,
}
_TREE_TYPES = ("main-topic", "topic", "slide", "term")
# Which parent types each type may sit under. The main-topic sits only at the root.
_PARENTS: dict[str, tuple[str, ...]] = {
    "main-topic": (),
    "topic": ("main-topic",),
    "slide": ("topic",),
    "term": ("slide",),
    "example": _TREE_TYPES,
    "exercise": _TREE_TYPES,
}

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# The page adds these prefixes to example and exercise labels, so no label may start with one.
_WORKED_PREFIX = re.compile(r"\s*(exempel|övning)\s*:", re.IGNORECASE)
_NO_CONTROL = "^[^\\u0000-\\u001f\\u007f-\\u009f]*$"
_NON_BLANK = "\\S"
_STAMP = "^(\\d+:[0-5]\\d|\\d+:[0-5]\\d:[0-5]\\d)$"
_MATH_CHECKS = {"prose": prose_problems, "calculation": calculation_problems}
_SCHEMA_ID = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True)
class OutlineSchema:
    """What `get_outline_schema` hands the LLM before it writes an Outline.

    `schema` is a JSON Schema, draft 2020-12, as a dict that `json.dumps`
    accepts. `samples` is two bare nodes the LLM can copy: an example first,
    then an exercise, each with LaTeX between `$...$` in its task and its
    answer, and LaTeX with no `$` in at least one step's calculation.
    """

    schema: dict
    samples: tuple[dict, dict]


def get_outline_schema() -> OutlineSchema:
    """Return the Outline's JSON Schema and a sample example node and exercise node.

    An Outline is one JSON object, the main-topic node. Every node is an
    object with a `type` and, for that type, exactly these parts, every one
    always present:

    - `main-topic`, `topic`, `slide` and `term`: `type`, `label`,
      `explanation` (a string), `stamps` (a list of strings such as `"4:34"`
      or `"1:10:05"`, no brackets), `slides` (a list of integers, Slide
      numbers counted from 1) and `children` (a list of nodes).
    - `example` and `exercise`: `type`, `label`, `stamps`, `slides`, `task`
      (a string), `steps` (a list of objects with exactly `calculation`, a
      string, and `reason`, a string) and `answer` (a string). They have no
      `explanation` and no `children`.

    `type`, `label`, `task` and each step's `calculation` must be non-blank.
    Every other part may be empty, `""` or `[]`. Math is LaTeX, always
    inline, never `$$`. A task, an answer, an explanation and a step's
    reason are prose with math between `$...$`, and a literal dollar sign is
    `\\$`. A step's calculation is LaTeX alone, with no `$`. Each step is one
    calculation, and its reason at most one short Swedish sentence on why.
    The schema's description says all of this. One table in this module
    says which parts each type has and which must be non-blank, and both the
    schema and the check are built from it, so making a part required is a
    one-line change.

    Nesting: the root is the one main-topic. A topic sits under the
    main-topic, a slide under a topic, and a term under a slide. An example or
    exercise sits under any node of the other four types, never under an
    example or exercise.

    The schema states all of the above, so an Outline that passes the schema
    passes the check's shape and nesting rules. The samples each pass the
    check when placed under a slide node. Calling this twice returns equal
    values.
    """
    return OutlineSchema(_schema(), _samples())


def check_outline(
    outline: object, *, duration_s: float | None, deck_pages: int | None
) -> tuple[OutlineProblem, ...]:
    """Return every problem with a parsed Outline, in Outline order, as `render_mindmap` describes them.

    `duration_s` is the Source's length in seconds, or None when there is no
    Source, so any stamp is a problem. `deck_pages` is the Deck's Slide count,
    or None when there is no Deck, so any Slide number is a problem.
    """
    check = _Check(duration_s, deck_pages)
    if not isinstance(outline, dict):
        check.add((), "the Outline must be one main-topic node, not a list or a value")
        return tuple(check.problems)
    if outline.get("type") != "main-topic":
        check.add((), "the root must be a main-topic node")
    check.node(outline, (), 1, None)
    return tuple(check.problems)


def _latex_message(key: str, broken: BrokenLatex) -> str:
    return f'{key} has LaTeX that cannot be drawn, "{broken.piece}": {broken.reason}'


def _node_path_label(node: object, position: int) -> str:
    """Return how a node stands in a label path: its label, or `#N` when the label is missing or blank."""
    label = node.get("label") if isinstance(node, dict) else None
    return label if isinstance(label, str) and label.strip() else f"#{position}"


class _Check:
    """Collects problems while walking an Outline, parents before children."""

    def __init__(self, duration_s: float | None, deck_pages: int | None) -> None:
        self.duration_s = duration_s
        self.deck_pages = deck_pages
        self.problems: list[OutlineProblem] = []

    def add(self, path: tuple[str, ...], message: str) -> None:
        self.problems.append(OutlineProblem(path, message))

    def node(self, node: object, parent_path: tuple[str, ...], position: int, parent: str | None) -> None:
        path = (*parent_path, _node_path_label(node, position))
        if not isinstance(node, dict):
            self.add(path, "a node must be an object")
            return
        kind = node.get("type")
        if kind not in _PARTS:
            self.add(path, "missing type" if "type" not in node else f"unknown type {_quoted(kind)}")
            return
        if parent is not None and parent not in _PARENTS[kind]:
            self.add(path, f"a {kind} node cannot sit under a {parent} node")
        parts = _PARTS[kind]
        for key in node:
            if key != "type" and key not in parts:
                self.add(path, f"{kind} nodes have no {_quoted(key)} part")
        for key, part in parts.items():
            if key not in node:
                self.add(path, f"missing {key}")
            else:
                self.part(path, key, node[key], part)
        self.label_prefix(path, node.get("label"))
        children = node.get("children") if "children" in parts else None
        if isinstance(children, list):
            for index, child in enumerate(children, start=1):
                self.node(child, path, index, kind)

    def part(self, path: tuple[str, ...], key: str, value: object, part: _Part) -> None:
        if not _has_kind(value, part.kind):
            self.add(path, f"{key} must be {_KIND_NAMES[part.kind]}")
        elif part.kind in ("text", "prose"):
            self.text(path, key, value, part)
        elif part.kind == "stamps":
            self.stamps(path, value)
        elif part.kind == "slides":
            self.slides(path, value)
        elif part.kind == "steps":
            for number, step in enumerate(value, start=1):
                self.step(path, number, step)

    def text(self, path: tuple[str, ...], key: str, value: str, part: _Part) -> None:
        if part.required and not value.strip():
            self.add(path, f"{key} is blank")
        if part.kind == "text" and _CONTROL.search(value):
            self.add(path, f"{key} holds a control character; escape every LaTeX backslash as \\\\")
        elif part.math is not None:
            for piece in _MATH_CHECKS[part.math](value):
                self.add(path, _latex_message(key, piece))

    def label_prefix(self, path: tuple[str, ...], label: object) -> None:
        prefix = _WORKED_PREFIX.match(label) if isinstance(label, str) else None
        if prefix:
            self.add(
                path,
                f"label starts with {_quoted(prefix.group(1).capitalize() + ':')}; use an example or exercise "
                "node and leave the prefix out, since the page adds it",
            )

    def step(self, path: tuple[str, ...], number: int, step: dict) -> None:
        for key in step:
            if key not in _STEP_PARTS:
                self.add(path, f"step {number} has no {_quoted(key)} part")
        for key, part in _STEP_PARTS.items():
            if key not in step:
                self.add(path, f"step {number} is missing {key}")
            else:
                self.part(path, f"step {number} {key}", step[key], part)

    def stamps(self, path: tuple[str, ...], stamps: list[str]) -> None:
        for stamp in stamps:
            seconds = stamp_seconds(f"[{stamp}]")
            if self.duration_s is None:
                self.add(path, f"stamp {_quoted(stamp)} has no Source to link to, so leave stamps empty")
            elif seconds is None:
                self.add(path, f"stamp {_quoted(stamp)} is malformed")
            elif seconds > self.duration_s:
                end = display_stamp(self.duration_s)
                self.add(path, f"stamp {_quoted(stamp)} is past the Source's end at {end}")

    def slides(self, path: tuple[str, ...], slides: list[int]) -> None:
        seen: set[int] = set()
        for number in slides:
            if self.deck_pages is None:
                self.add(path, f"Slide {number} has no Deck to link to, so leave slides empty")
            elif number < 1:
                self.add(path, f"Slide {number} is below 1")
            elif number > self.deck_pages:
                self.add(path, f"Slide {number} is past the Deck's last Slide, {self.deck_pages}")
            elif number in seen:
                self.add(path, f"Slide {number} is listed twice")
            seen.add(number)


_KIND_NAMES = {
    "text": "a string",
    "prose": "a string",
    "stamps": "a list of stamp strings",
    "slides": "a list of integer Slide numbers",
    "nodes": "a list of nodes",
    "steps": "a list of step objects",
}


def _has_kind(value: object, kind: str) -> bool:
    if kind in ("text", "prose"):
        return isinstance(value, str)
    if not isinstance(value, list):
        return False
    if kind == "stamps":
        return all(isinstance(item, str) for item in value)
    if kind == "slides":
        return all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    if kind == "steps":
        return all(isinstance(item, dict) for item in value)
    return True


def _quoted(value: object) -> str:
    return f'"{value}"' if isinstance(value, str) else repr(value)


def _schema() -> dict:
    """Return the JSON Schema built from the parts table and the nesting rules."""
    defs = {kind: _node_schema(kind) for kind in _PARTS}
    defs["step"] = _object_schema(_STEP_PARTS, {})
    return {
        "$schema": _SCHEMA_ID,
        "title": "Munin Outline",
        "description": (
            "One main-topic node at the root. Every node carries every part its type has; "
            "a part that may be empty is written as \"\" or []. Stamps are \"m:ss\" or \"h:mm:ss\" "
            "without brackets, and Slide numbers count from 1. Math is LaTeX, so escape every "
            "backslash as \\\\ in JSON. Task, answer, explanation and a step's reason are prose with math "
            "between $...$, never $$, and a literal dollar sign is \\\\$. A step's calculation is LaTeX "
            "alone, with no $. Each step is one calculation, and its reason one short Swedish sentence."
        ),
        "$ref": "#/$defs/main-topic",
        "$defs": defs,
    }


def _node_schema(kind: str) -> dict:
    children = [child for child, parents in _PARENTS.items() if kind in parents]
    nodes = {"type": "array", "items": {"oneOf": [{"$ref": f"#/$defs/{child}"} for child in children]}}
    return _object_schema(_PARTS[kind], {"type": {"const": kind}}, nodes)


def _object_schema(parts: dict[str, _Part], extra: dict, nodes: dict | None = None) -> dict:
    properties = dict(extra)
    for key, part in parts.items():
        properties[key] = _part_schema(part.kind, part.required, nodes)
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _part_schema(kind: str, required: bool, nodes: dict | None) -> dict:
    if kind == "prose":
        return {"type": "string"}
    if kind == "text":
        text = {"type": "string", "pattern": _NO_CONTROL}
        return {"allOf": [text, {"pattern": _NON_BLANK}]} if required else text
    if kind == "stamps":
        return {"type": "array", "items": {"type": "string", "pattern": _STAMP}}
    if kind == "slides":
        return {"type": "array", "items": {"type": "integer", "minimum": 1}, "uniqueItems": True}
    if kind == "steps":
        return {"type": "array", "items": {"$ref": "#/$defs/step"}}
    return nodes


def _samples() -> tuple[dict, dict]:
    example = {
        "type": "example",
        "label": "Förenkla ett bråk",
        "stamps": [],
        "slides": [],
        "task": "Förenkla $\\frac{6}{8}$",
        "steps": [
            {"calculation": "\\frac{6}{8} = \\frac{2 \\cdot 3}{2 \\cdot 4}", "reason": "faktorisera"},
            {"calculation": "\\frac{2 \\cdot 3}{2 \\cdot 4} = \\frac{3}{4}", "reason": "förkorta med 2"},
        ],
        "answer": "$\\frac{3}{4}$",
    }
    exercise = {
        "type": "exercise",
        "label": "Matrisprodukt",
        "stamps": [],
        "slides": [],
        "task": "Beräkna $\\begin{pmatrix} 1 & 2 \\end{pmatrix} \\begin{pmatrix} 3 \\\\ 4 \\end{pmatrix}$",
        "steps": [{"calculation": "1 \\cdot 3 + 2 \\cdot 4", "reason": "rad gånger kolonn"}],
        "answer": "$\\begin{pmatrix} 11 \\end{pmatrix}$",
    }
    return example, exercise
