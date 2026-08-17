#!/usr/bin/env python3
"""Lint the GitHub Actions workflow files so their YAML cannot silently break.

The release and CI workflows are the only place where a signing step can be
dropped or a branch mis-indented without a single test noticing — the workflows
are not executed by ``pytest``, and a YAML typo ships a release that *claims* to
be signed and is not.  This script is the guard:

  * every ``.github/workflows/*.yml`` must parse under a small, self-contained
    YAML subset checker (block mappings/sequences, flow collections, quoted
    scalars, block scalars ``|``/``>`` — the features these workflows actually
    use; PyYAML cannot be installed here);
  * ``release.yml`` must carry the signing machinery the release depends on:
    a ``build`` and a ``publish`` job, a four-row build matrix, structurally
    distinct SIGNED and UNSIGNED build steps, a verification step that runs
    ``scripts/verify_signing.py``, and an unsigned-marker step.

Exit 0 = all workflows parse and ``release.yml`` has its machinery; 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO / ".github" / "workflows"


class WorkflowLintError(ValueError):
    def __init__(self, line: int, message: str) -> None:
        self.line = line
        super().__init__(f"line {line}: {message}")


# ---------------------------------------------------------------------------
# A minimal YAML subset loader for GitHub Actions workflows.
# ---------------------------------------------------------------------------

_BLOCK_SCALAR_HINTS = ("|", ">")


def _strip_comment(line: str) -> str:
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in ('"', "'"):
                quote = c
            elif c == "#" and (i == 0 or line[i - 1] in " \t"):
                return line[:i]
        i += 1
    return line


def _indent(content: str, lineno: int) -> int:
    count = 0
    for c in content:
        if c == " ":
            count += 1
        elif c == "\t":
            raise WorkflowLintError(lineno, "tab characters are not allowed in indentation")
        else:
            break
    return count


def _is_block_scalar_rest(rest: str) -> str | None:
    """Return the block scalar indicator when ``rest`` is one (``|``, ``>-`` ...)."""
    r = rest.strip()
    if not r:
        return None
    if r[0] not in _BLOCK_SCALAR_HINTS:
        return None
    tail = r[1:]
    if tail and tail[0] in "+-":
        tail = tail[1:]
    if tail and not tail.isdigit():
        return None
    return r[0]


def _has_top_level_colon(text: str) -> bool:
    """True when ``text`` has a ``:`` outside quotes and flow brackets."""
    quote: str | None = None
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in ('"', "'"):
                quote = c
            elif c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
            elif c == ":" and depth == 0:
                return True
        i += 1
    return False


def _split_key(content: str, lineno: int) -> tuple[str, str | None]:
    """Split ``key: value`` at the first ``:`` outside quotes/brackets."""
    quote: str | None = None
    depth = 0
    i = 0
    n = len(content)
    while i < n:
        c = content[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in ('"', "'"):
                quote = c
            elif c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
            elif c == ":" and depth == 0:
                key = _strip_quotes(content[:i].strip())
                if not key:
                    raise WorkflowLintError(lineno, "empty mapping key")
                rest = content[i + 1 :].strip()
                return key, (rest if rest else None)
        i += 1
    raise WorkflowLintError(lineno, f"expected 'key: value', got {content!r}")


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    return s


def _check_flow_balance(text: str, lineno: int) -> None:
    """Validate that flow brackets and quotes are balanced (syntax only)."""
    quote: str | None = None
    stack: list[str] = []
    pairs = {"}": "{", "]": "["}
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
        else:
            if c in ('"', "'"):
                quote = c
            elif c in "{[":
                stack.append(c)
            elif c in "}]":
                if not stack or stack[-1] != pairs[c]:
                    raise WorkflowLintError(lineno, f"unbalanced flow bracket in {text!r}")
                stack.pop()
        i += 1
    if quote is not None:
        raise WorkflowLintError(lineno, "unterminated quote")
    if stack:
        raise WorkflowLintError(lineno, "unterminated flow bracket")


class _Loader:
    def __init__(self, lines: list[tuple[int, str]]) -> None:
        self.lines = lines
        self.pos = 0

    def _peek(self) -> tuple[int, str] | None:
        while self.pos < len(self.lines):
            lineno, content = self.lines[self.pos]
            if content.strip():
                return lineno, content
            self.pos += 1
        return None

    def parse(self) -> object:
        first = self._peek()
        if first is None:
            raise WorkflowLintError(1, "empty document")
        return self._block(_indent(first[1], first[0]))

    def _block(self, indent: int) -> object:
        lineno, content = self._peek()
        if content.lstrip().startswith("- ") or content.lstrip() == "-":
            return self._sequence(indent)
        return self._mapping(indent)

    def _mapping(self, indent: int) -> dict:
        out: dict = {}
        while True:
            entry = self._peek()
            if entry is None:
                break
            lineno, content = entry
            cur = _indent(content, lineno)
            if cur < indent:
                break
            if cur > indent:
                raise WorkflowLintError(lineno, "unexpected indentation")
            if content.lstrip().startswith("-"):
                raise WorkflowLintError(lineno, "sequence item where mapping key expected")
            key, rest = _split_key(content, lineno)
            self.pos += 1
            out[key] = self._mapping_value(rest, indent, lineno)
        return out

    def _sequence(self, indent: int) -> list:
        out: list = []
        while True:
            entry = self._peek()
            if entry is None:
                break
            lineno, content = entry
            cur = _indent(content, lineno)
            if cur < indent:
                break
            if cur > indent:
                raise WorkflowLintError(lineno, "unexpected indentation")
            stripped = content.lstrip()
            if not stripped.startswith("-"):
                break
            rest = stripped[1:].strip()
            self.pos += 1
            if rest == "":
                nxt = self._peek()
                if nxt is not None and _indent(nxt[1], nxt[0]) > indent:
                    out.append(self._block(_indent(nxt[1], nxt[0])))
                else:
                    out.append(None)
            elif _has_top_level_colon(rest):
                # `- key: value` — a mapping that continues on following lines
                # at the key's column (`- ` is two characters).
                out.append(self._mapping_after_dash(rest, lineno, cur + 2))
            else:
                _check_flow_balance(rest, lineno)
                out.append(rest)
        return out

    def _mapping_after_dash(self, rest: str, lineno: int, key_col: int) -> dict:
        """Parse a mapping whose first entry sits on a ``- key: value`` line."""
        result: dict = {}
        key, value = _split_key(rest, lineno)
        result[key] = self._mapping_value(value, key_col, lineno)
        while True:
            entry = self._peek()
            if entry is None:
                break
            lineno2, content2 = entry
            cur2 = _indent(content2, lineno2)
            if cur2 < key_col:
                break
            if cur2 > key_col:
                raise WorkflowLintError(lineno2, "unexpected indentation")
            if content2.lstrip().startswith("-"):
                break
            key2, rest2 = _split_key(content2, lineno2)
            self.pos += 1
            result[key2] = self._mapping_value(rest2, key_col, lineno2)
        return result

    def _mapping_value(self, rest: str | None, key_col: int, lineno: int) -> object:
        """The value for a mapping key: inline scalar, nested block, or block scalar."""
        if rest is None:
            nxt = self._peek()
            if nxt is not None and _indent(nxt[1], nxt[0]) > key_col:
                return self._block(_indent(nxt[1], nxt[0]))
            return None
        bs = _is_block_scalar_rest(rest)
        if bs is not None:
            return self._consume_block_scalar(key_col)
        _check_flow_balance(rest, lineno)
        return rest

    def _consume_block_scalar(self, key_indent: int) -> str:
        """Consume a ``|``/``>`` block-scalar body and return its dedented text."""
        body: list[str] = []
        base_indent: int | None = None
        while self.pos < len(self.lines):
            lineno, content = self.lines[self.pos]
            if not content.strip():
                body.append("")
                self.pos += 1
                continue
            ind = _indent(content, lineno)
            if ind <= key_indent:
                break
            if base_indent is None:
                base_indent = ind
            body.append(content[base_indent:])
            self.pos += 1
        while body and body[-1] == "":
            body.pop()
        return "\n".join(body)


def load_workflow(text: str) -> object:
    lines = [(i, _strip_comment(raw).rstrip()) for i, raw in enumerate(text.splitlines(), start=1)]
    return _Loader(lines).parse()


# ---------------------------------------------------------------------------
# Structural checks over release.yml
# ---------------------------------------------------------------------------


def _step_names(tree: dict) -> list[str]:
    build = (tree.get("jobs") or {}).get("build") or {}
    steps = build.get("steps") or []
    names: list[str] = []
    for step in steps:
        if isinstance(step, dict) and step.get("name"):
            names.append(step["name"])
    return names


def _step_runs(tree: dict) -> list[str]:
    build = (tree.get("jobs") or {}).get("build") or {}
    steps = build.get("steps") or []
    runs: list[str] = []
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("run"), str):
            runs.append(step["run"])
        elif isinstance(step, dict) and isinstance(step.get("run"), list):
            runs.extend(str(r) for r in step["run"])
    return runs


def release_structure_problems(tree: object) -> list[str]:
    """The release.yml invariants the signing work depends on."""
    problems: list[str] = []
    if not isinstance(tree, dict):
        return ["release.yml is not a mapping"]

    jobs = tree.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        problems.append("release.yml has no 'jobs' mapping")
        return problems

    if "build" not in jobs:
        problems.append("missing 'build' job")
    if "publish" not in jobs:
        problems.append("missing 'publish' job")

    build = jobs.get("build")
    if isinstance(build, dict):
        strategy = build.get("strategy") or {}
        matrix = strategy.get("matrix") or {}
        include = matrix.get("include")
        if isinstance(include, list):
            platforms = [r.get("platform") for r in include if isinstance(r, dict)]
            expected = ["linux", "macos", "macos", "windows"]
            if sorted(platforms) != sorted(expected):
                problems.append(
                    f"build matrix platforms {platforms!r} != expected {expected!r}"
                )
        else:
            problems.append("build matrix has no 'include' list")

    names = _step_names(tree)
    runs = _step_runs(tree)

    if not any("verify_signing.py" in r for r in runs):
        problems.append("no step runs scripts/verify_signing.py (the signed build is never verified)")
    if not any("SIGNING-STATUS.txt" in r for r in runs):
        problems.append("no step writes SIGNING-STATUS.txt (the unsigned marker is missing)")
    if not any("UNSIGNED" in n for n in names):
        problems.append("no step is named UNSIGNED (the unsigned path is not visibly distinct)")
    if not any("SIGNED" in n or "Verify" in n for n in names):
        problems.append("no step is named SIGNED/Verify (the signed path is not visibly distinct)")

    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def lint(workflows_dir: Path) -> int:
    files = sorted(workflows_dir.glob("*.yml"))
    if not files:
        print(f"error: no workflow files under {workflows_dir}", file=sys.stderr)
        return 1

    failures = 0
    release_tree: object = None
    for path in files:
        try:
            tree = load_workflow(path.read_text())
        except WorkflowLintError as exc:
            print(f"{path.relative_to(REPO)}: YAML lint failed — {exc}", file=sys.stderr)
            failures += 1
            continue
        if path.name == "release.yml":
            release_tree = tree
        print(f"{path.relative_to(REPO)}: parses")

    if release_tree is None:
        print("error: release.yml not found under the workflows dir", file=sys.stderr)
        return 1

    for problem in release_structure_problems(release_tree):
        print(f"release.yml: {problem}", file=sys.stderr)
        failures += 1

    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="lint the GitHub Actions workflows")
    parser.add_argument("--workflows", default=str(WORKFLOWS_DIR), help="workflows dir (default: %(default)s)")
    args = parser.parse_args(argv)

    code = lint(Path(args.workflows))
    if code == 0:
        print("workflow lint: ok")
    return code


if __name__ == "__main__":
    sys.exit(main())
