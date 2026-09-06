# Contributing to acervo-dedup

## Commit messages

**English, always — [Conventional Commits](https://www.conventionalcommits.org/), imperative mood.** This doesn't depend on whether the repo is closed or has an external audience — it's the standard for anyone programming seriously today, regardless of who reads it later. Identifiers stay in Portuguese; comments and docstrings are also in English (see below).

```
<type>(<scope>): short imperative summary, ≤50 chars

Body explaining WHY this change exists, not what changed — the diff
already shows what. Wrap at ~72 columns.
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`.

References: [conventionalcommits.org](https://www.conventionalcommits.org/) for the format, Chris Beams's seven rules ("How to Write a Git Commit Message") for the prose. No attribution line for code-generation tools.

## Comments and docstrings

**English, always.** Same reason as commit messages: it's the standard for anyone programming seriously, regardless of who reads it later.

What doesn't change language:

| surface | language | why |
|---|---|---|
| comment, docstring, commit message, README, project docs | English | technical/portfolio audience, not necessarily Brazilian |
| identifier (`agrupar_exatas`, `quarentena_dir`) | Portuguese | renaming is risky refactoring, and the domain vocabulary belongs to the acervo |
| CLI output, interface text | Portuguese | the user is Brazilian; the tool speaks to her |

A comment exists to explain **why**, not what. If it's describing what the line does, the line is the problem.

## Before opening a PR

The cost of a mistake here is the highest in the suite: deleting the original is irreversible (see `CLAUDE.md`). Any change to `quality.py` (representative policy) or `quarantine.py` deserves a run of `python -m unittest discover -s tests` — the suite already covers real disk and SQLite, not just synthetic data — before the PR, not after.

## The graphical layer

`src/acervo_dedup/gui/` is presentation, and only that. The rule that keeps it honest: it doesn't import `exact`, `perceptual`, `quality`, or `quarantine` — it runs `acervo-dedup scan` and `acervo-dedup isolar` as a subprocess and streams their `stdout`.

This isn't architectural purism, it's invariant 1 surviving the existence of buttons: if the only way to move a file is through the command that was already auditable, no interface bug can invent a new path to disk. Any decision rule that shows up in this folder is in the wrong place.
