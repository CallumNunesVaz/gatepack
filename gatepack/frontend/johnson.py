"""Johnson-counter topology detection (§9.4).

C1 detects an FSM whose transition structure is a simple, un-branched cycle and
*suggests* a ``JOHN10`` (74HC4017) macro — never applies it.  Branching
transitions break the topology and the suggestion is withheld.
"""

from __future__ import annotations

from typing import Sequence


def outgoing_map(
    transitions: Sequence[tuple[str, str]],
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for src, dst in transitions:
        out.setdefault(src, []).append(dst)
    return out


def suggest_johnson(
    states: Sequence[str],
    transitions: Sequence[tuple[str, str]],
    initial: str,
) -> str | None:
    """Return a suggestion string if the FSM is a simple cycle, else ``None``.

    A simple cycle means every state has exactly one outgoing transition and the
    transitions, followed from ``initial``, visit every state exactly once before
    returning to ``initial``.
    """
    if not transitions:
        return None

    outgoing = outgoing_map(transitions)

    for state in states:
        if len(outgoing.get(state, [])) != 1:
            return None

    visited: list[str] = []
    current = initial
    seen: set[str] = set()
    while current not in seen:
        if current not in outgoing:
            return None
        seen.add(current)
        visited.append(current)
        current = outgoing[current][0]

    if set(visited) != set(states):
        return None

    cycle = " -> ".join((*visited, visited[0]))
    return (
        f"state topology is a simple {len(visited)}-state cycle ({cycle}); "
        "consider a JOHN10 (74HC4017) one-hot sequencer macro instead of "
        "individual flops — apply it manually, never automatically (§9.4)"
    )
