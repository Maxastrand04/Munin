"""The Outline's JSON format: its schema, its samples, and the check every render runs first."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OutlineSchema:
    """What `get_outline_schema` hands the LLM before it writes an Outline.

    `schema` is a JSON Schema, draft 2020-12, as a dict that `json.dumps`
    accepts. `samples` is two bare nodes the LLM can copy: an exempel first,
    then an övning, each with LaTeX in its task, in at least one step's
    calculation, and in its answer.
    """

    schema: dict
    samples: tuple[dict, dict]


def get_outline_schema() -> OutlineSchema:
    """Return the Outline's JSON Schema and a sample exempel node and övning node.

    An Outline is one JSON object, the main-topic node. Every node is an
    object with a `type` and, for that type, exactly these parts, every one
    always present:

    - `main-topic`, `topic`, `slide` and `term`: `type`, `label`,
      `explanation` (a string), `stamps` (a list of strings such as `"4:34"`
      or `"1:10:05"`, no brackets), `slides` (a list of integers, Slide
      numbers counted from 1) and `children` (a list of nodes).
    - `exempel` and `övning`: `type`, `label`, `stamps`, `slides`, `task`
      (a string), `steps` (a list of objects with exactly `calculation`, a
      string, and `reason`, a string) and `answer` (a string). They have no
      `explanation` and no `children`.

    `type`, `label`, `task` and each step's `calculation` must be non-blank.
    Every other part may be empty, `""` or `[]`. Task, calculations and
    answer are LaTeX, and reasons are short Swedish. One table in this module
    says which parts each type has and which must be non-blank, and both the
    schema and the check are built from it, so making a part required is a
    one-line change.

    Nesting: the root is the one main-topic. A topic sits under the
    main-topic, a slide under a topic, and a term under a slide. An exempel or
    övning sits under any node of the other four types, never under an
    exempel or övning.

    The schema states all of the above, so an Outline that passes the schema
    passes the check's shape and nesting rules. The samples each pass the
    check when placed under a slide node. Calling this twice returns equal
    values.
    """
    raise NotImplementedError
