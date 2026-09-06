# acervo-dedup

Redundancy detection in large photo collections. Windows desktop app, with the same engine exposed as a CLI.

Answers **one** question: *are these files the same content?*

## Two passes

1. **Exact** — screened by byte size first (a file with a unique size is discarded without any I/O), then block-wise SHA-256 for the remaining candidates. Filename-agnostic, since names are usually chaotic after disk recovery.
2. **Perceptual** — perceptual hashing to catch recompression, resizing, and screenshots of the same photo, which the exact pass misses.

## The cost of a mistake drives the design

Deleting the original is irreversible. So:

- The engine **isolates**, it never deletes. Removal is always a separate, explicit second step.
- The group's representative is the one with the oldest creation metadata, and the choice is recorded along with the reason.
- A locked-file or permission-denied exception doesn't bring down the whole scan.

## Two destinations, by confidence level

What the exact pass finds and what the perceptual pass finds don't carry the same confidence, so they don't go to the same place:

| source | destination | why |
|---|---|---|
| **exact** group | `quarentena` | The bytes are identical. Either the SHA-256 matches or it doesn't — no false positive is possible. |
| **perceptual** group | `revisao` | Comes from similarity, which can be wrong. Could be a one-of-a-kind photo. A human-decision queue, never automatic discard. |

The split is structural, by design. In a real measurement on a facial-reference folder, **4 of 11 perceptual candidates were a burst** of distinct photos — same pose, different instants and framing — not copies. Tightening the distance threshold wouldn't have fixed it: the burst measured a distance of 2, within any defensible cutoff. A threshold picked to make one specific case pass is a guess; splitting by confidence level is a guarantee.

`isolar --somente quarentena` moves only the safe-to-discard set, without touching the review queue.

## Output

Writes to the `duplicatas` table of `acervo`. Also exports a JSON report with `duplicate_groups`, recoverable space, and each group's representative.

## Interface

Native Windows window (WebView2, the Edge runtime that ships with Windows 11), served by a local server that **only listens on `127.0.0.1`**, with a session token generated on every start. Nothing leaves the machine.

The interface is a **shell**: it contains no detection, representative-selection, or destination logic. It runs `scan` and `isolar` as a subprocess and streams their `stdout` live. Deleting the entire `src/acervo_dedup/gui/` folder wouldn't change a single bit of the engine's output.

The "isolate, never delete" invariant is what the screen renders:

- **There is no delete button** anywhere in the interface.
- `isolar` always opens in **dry-run**. Actually moving files requires typing `ISOLAR` into a dialog that states how many files and where.
- **Color is semantic, not decoration.** The palette comes from *Operários* (Tarsila do Amaral, 1933): ochre = certainty (byte-identical copy, safe discard), terracotta = similarity (fallible, human decision), brick = irreversible action, sky = neutral information.

Four steps, in order of increasing cost of error: **Scan → Result → Review → Isolate** (`Varredura → Resultado → Conferência → Isolar` in the interface, which stays in Portuguese — see [Language](CONTRIBUTING.md)). The last three stay locked until a report exists.

## Installation

Requires **Windows 10/11 with the WebView2 runtime** (already installed on Windows 11) for the native window. To run from source or use just the CLI, requires **Python 3.10 or newer**. Tested on Windows 11 with Python 3.14.

There are **two programs**, and the order matters: `acervo` scans the disk, computes SHA-256 and a perceptual hash, and writes the index; `acervo-dedup` reads that index and decides what's a duplicate. The split exists so the image gets decoded **exactly once** across the whole suite — that's why `acervo-dedup` has no dependency on Pillow: it reads `phash` from the database instead of reopening the photo.

### Option A — executable (normal use)

Unzip `acervo-dedup-windows.zip` into a folder and **double-click `acervo-dedup-gui.exe`**. No installer, no registry entries, no background service: deleting the folder uninstalls it.

The folder ships **two binaries**, and both are required:

| binary | subsystem | role |
|---|---|---|
| `acervo-dedup-gui.exe` | windowed | the one you open; shows no console |
| `acervo-dedup.exe` | console | the engine; the window runs it and reads its `stdout` for the live log |

Don't separate the two or rename the second one — the window looks for `acervo-dedup.exe` right next to itself.

### Option B — from source

Both repositories are **private** (closed source, Obsn Studios): cloning requires a credential with access.

```bash
git clone https://github.com/ferlief/acervo.git
git clone https://github.com/ferlief/acervo-dedup.git
```

Use a virtual environment — installing a package into the global Python is like writing straight into the acervo: it works until the day another project needs a different version.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ./acervo
pip install -e "./acervo-dedup[gui]"
```

The `[gui]` extra brings in `pywebview` (the native window). Without it the engine and CLI work the same, and `gui` falls back to the browser — the window dependency is optional on purpose: scanning an external drive over SSH shouldn't need a graphical toolkit installed.

Confirm it installed:

```bash
python -m acervo.cli --help
python -m acervo_dedup.cli --help
```

**On Windows, `pip` often warns that the `Scripts` folder isn't on PATH.** If `acervo-dedup` isn't recognized as a command, use the `python -m acervo_dedup.cli ...` form instead — it always works, without touching PATH. All examples below use that form.

### Building the executable

```bash
pip install -e ".[build]"
python -m PyInstaller --noconfirm --clean packaging/acervo-dedup.spec
```

Lands in `dist/acervo-dedup/` (~36 MB). It's `onedir`, not `onefile`, on purpose: the window runs the CLI once per scan, and a `onefile` build would re-extract the whole package to a temp folder on every run.

## Using the interface

Open `acervo-dedup-gui.exe`. The four steps in the side rail are the correct order, and each one only unlocks once the previous produced a result:

1. **Scan** (`Varredura`) — enter the roots (or leave blank to use the config) and click *Iniciar varredura*. The engine's output appears line by line. Nothing is moved at this step.

   > **If a red error about a missing database shows up:** `acervo` needs to run first. The two programs work as a pair — `acervo` looks at the photos and writes down what it saw; `acervo-dedup` reads those notes. Without the first part, the second has nothing to read.

2. **Result** (`Resultado`) — how much space can be recovered, split into `quarentena` (byte-identical copy) and `revisao` (similar). Read errors are listed here, not hidden.

3. **Review** (`Conferência`) — group by group, with the representative, the reason for the choice, and each candidate's distance. Filter by method, sort by space, search by path or `sha256`. **It's worth eyeballing the perceptual groups** — those are the fallible ones.

4. **Isolate** (`Isolar`) — start with *Simular* (simulate). If the list makes sense, *Mover de fato* (actually move) requires typing the word `ISOLAR`.

To point to a different config, open it from the terminal:

```bash
acervo-dedup-gui.exe --config dedup-config.yaml
```

## Using the CLI

The same engine, without the window. This is the path for automation, remote machines, and scripts.

### 1. Configure

```bash
cp acervo/config.example.yaml acervo-config.yaml
cp acervo-dedup/config.example.yaml dedup-config.yaml
```

In both files, point `banco.caminho` to the **same** `.sqlite3` — that's what links the two programs together — and `varredura.raizes` to the folder to clean up. In `dedup-config.yaml`, also check `quarentena.diretorio` and `revisao.diretorio`.

No path is hardcoded: the same command line runs against a test folder or the entire acervo, just by swapping the config.

### 2. Index

```bash
python -m acervo.cli --config acervo-config.yaml indexar
```

Scans, hashes, and decodes each image once. This is the only slow part — the following steps are fast.

### 3. Detect

```bash
python -m acervo_dedup.cli --config dedup-config.yaml scan
```

**Moves nothing.** Writes the `duplicatas` table and the JSON report, and prints how much space is recoverable, split by confidence level.

### 4. Review before touching anything

Open the JSON report. Each group carries the representative (the one that stays), the reason for the choice, and the candidates with their `destino`. It's worth eyeballing the `perceptual` groups — those are the fallible ones.

### 5. Isolate the safe discard set

First in dry-run, which is the default:

```bash
python -m acervo_dedup.cli --config dedup-config.yaml isolar --somente quarentena
```

If the list makes sense, run:

```bash
python -m acervo_dedup.cli --config dedup-config.yaml isolar --somente quarentena --execute
```

Moves only the byte-identical copies. The subfolder structure is preserved, and nothing is overwritten (a name collision gets a `_dup1` suffix).

### 6. Decide on the similar ones

```bash
python -m acervo_dedup.cli --config dedup-config.yaml isolar --somente revisao --execute
```

This is **not discard** — it's a decision queue. Look through the `revisao` folder and return to the acervo whatever turns out to be a one-of-a-kind photo.

### 7. Deleting — only you

The program never deletes. After reviewing the quarantine, deleting the folder is your own choice, outside the tool. That's the step that actually recovers disk space.

## Development

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[build]"
python -m unittest discover -s tests
```

The suite covers the representative policy, both groupings, routing between the two destinations, and an end-to-end test against real disk and SQLite. **Any change to `quality.py` or `quarantine.py` runs the suite before the commit, not after** — that's where a mistake costs lost data.

Conventions (details in `CONTRIBUTING.md`):

- **Commits in English**, Conventional Commits, imperative mood.
- **Comments and docstrings in English.** Identifiers and interface text stay in Portuguese.
- The `gui/` layer can't import `exact`, `perceptual`, `quality`, or `quarantine`. If it needs to, the rule is in the wrong place.

## Status

**Implemented.** Engine in Python (`src/acervo_dedup/`), ported from the eight iterations of the source prototype (`acervo-prototipo/dedup_fase1.py` … `dedup_fase8.py`), not copied — the exact and perceptual passes use the same logic already tested against real disk data (size screening, block-wise SHA-256, perceptual hashing with multi-partition/LSH indexing, aspect-ratio guard), adapted to the `acervo/esquema.sql` contract.

Two deliberate differences from the prototype, required by the suite's contract:

- The perceptual pass **reads** `phash`/`largura`/`altura` from `arquivos` instead of reopening the image — that's the whole point of `sinais(fonte=exif)` in the schema: giving this program what it needs without re-decoding.
- The representative policy is more specific than described above: the exact group uses the oldest creation date; the perceptual group uses measurable quality (RAW > resolution > original-vs-edited via EXIF Software > lowest compression loss via JPEG quantization sum), tie-broken by date. See `src/acervo_dedup/quality.py`.

Commands: `acervo-dedup scan` (detects and writes the report + `duplicatas`, never moves anything), `acervo-dedup isolar` (moves to `quarentena`/`revisao` according to confidence level, dry-run by default, `--execute` to actually move, `--somente` to handle one class at a time), and `acervo-dedup gui` (native window; `--navegador` forces the browser tab).

The graphical interface (`src/acervo_dedup/gui/`) came after the engine and didn't change it: it runs the two commands above as a subprocess. Windows packaging lives in `packaging/`.

## License and monetization

Closed source, under Obsn Studios.

Free for local personal use, no artificial limit. A symbolic honor-based commercial license for professional use, Obsidian-style. No aggressive paywall, no recurring subscription.
