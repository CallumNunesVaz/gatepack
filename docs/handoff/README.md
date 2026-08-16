# Delegation handoff

Prompts staged for the next fan-out, kept here because the scratchpad is
session-scoped and has been cleared mid-work once already.

| file | package | status |
|---|---|---|
| `prompt-mcell.md` | **M8** — macro verification made real; a wrong `CNT4.v` must fail | written, not launched |
| `prompt-packed.md` | **M15** — `gatepack packed-netlist` + render the packed and overlay layers | written, not launched |
| `prompt-select.md` | **M16** — package and property cross-highlights | written, not launched |
| (not yet written) | **M18** — ship the Python core and toolchain inside the app | to write |
| `delegation-rules.md` | the shared rules block appended to each | — |

Worktrees `../gatepack-wt-{mcell,packed,select,ship}` exist on branches
`deepseek/{mcell,packed,select,ship}3`, all at the same clean baseline, with
`.venv` and `app/node_modules` symlinked and `.gpout/` created.

Launch staggered ~40s apart: four simultaneous `opencode` starts lock its
SQLite session store and two die instantly with `database is locked`.
