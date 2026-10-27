---
description: "How imgsqueeze gets pngquant and oxipng: pinned versions resolved only through mise in imgsqueeze/tools.py, the environment variable override, measured mise behavior, the error message contract, licensing, and the delivery options that were rejected. Read when changing imgsqueeze/tools.py, when a PNG fails with exit code 3, or before changing how the binaries are found."
---

# External Tools

The PNG engines of `02-compression-engines.md` need two binaries. Everything else needs only Pillow.

---

## 1. The pins

`imgsqueeze/tools.py` declares each binary as a `ToolSpec`:

| Constant | Binary | mise tool | Version | mise backend | Override variable |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `PNGQUANT` | pngquant | `conda:pngquant` | 3.0.3 | conda (conda-forge) | `IMGSQUEEZE_PNGQUANT` |
| `OXIPNG` | oxipng | `oxipng` | 10.2.1 | aqua (GitHub Releases) | `IMGSQUEEZE_OXIPNG` |

- pngquant is not in the mise registry, so it comes from conda-forge through the conda backend, which also installs the shared libraries (libpng and others) the conda build links against. 3.0.3 is upstream's latest tag; conda-forge has it for osx-arm64, osx-64, linux-64 and win-64.
- oxipng is in the mise registry; the aqua backend verifies the GitHub Releases checksum.
- The pinned version is also the minimum accepted from an override variable.

---

## 2. Resolution order (`resolve_tool`)

1. **Override variable.** When set, the path must be an executable file whose `--version` is at least the pinned version, compared as integer tuples (10.10.0 > 10.2.1). Otherwise it is an error: there is **no fallback** to mise, so a typo is never silently ignored.
2. **`mise which <name> --tool <mise_tool>@<version>`.** It picks that exact version whatever the config says. mise still **parses** the `mise.toml` of the current folder and its parents, and fails on one that is broken or untrusted (an `[env]` section is enough), which would break every PNG in such a blog repo. So `tools._run` runs every command in a fresh empty `tempfile.TemporaryDirectory` (`cwd=`). `tests/test_tools.py::test_project_mise_config_is_not_read` guards this.
3. **`mise install <mise_tool>@<version>`**, then step 2 again.
4. **`<binary> --version`** gives the version reported in `ResolvedTool` and the JSON `tools` field.

Rules, and why:

- **Never search `PATH`.** A Homebrew pngquant of another version would give different results on another machine.
- **Never `mise use -g`, never shims.** `use -g` rewrites the user's global config; a shim resolves whatever version the current folder's config selects, not the pin.
- **mise itself is never installed by imgsqueeze.** Missing mise is an error that links to its install page (`MISE_INSTALL_URL`).
- **Resolution runs once, in the main process,** before the worker pool starts (`runner.optimize`), and only when a pending image is a PNG. Workers receive absolute paths in `PngTools`.

Measured with mise 2026.7.0 (2026-10-26):

- `mise which --tool` does **not** install a missing version; it fails with exit code 1. The explicit `mise install` step is therefore required.
- `mise install` writes no config file (checked with every mise config and data directory redirected to a sandbox).
- Both installs give native arm64 binaries on macOS, under `~/.local/share/mise/installs/`.

---

## 3. Failure contract

Every failure raises `ToolUnavailableError`, whose message comes from `_explain` and is meant to be shown to a user as is: which tool and version is needed, the reason (mise missing, the `mise install` output, a bad override path or version, a timeout), and three fixes (`mise install <spec>`, install mise, set the override variable).

Effects elsewhere: in `optimize`, only PNG files fail (`Result.missing_tools`), the rest of the batch continues, and the CLI exits with 3 and prints the message once on stderr. `imgsqueeze setup` exits with 3. A batch without PNG files never touches mise.

Subprocess calls use timeouts (`_WHICH_TIMEOUT` 60 s, `_INSTALL_TIMEOUT` 600 s, `_VERSION_TIMEOUT` 30 s); a timeout or an `OSError` becomes `ToolUnavailableError` too.

---

## 4. Licensing

imgsqueeze is MIT. pngquant is GPL-3.0 or commercial. imgsqueeze runs it as a separate process, never links or bundles it, and mise installs it on the user's machine. pngquant's licensing page states that the images it produces are not covered by its license. Running a program as a separate process is generally treated as aggregation, not a derivative work. The README credits pngquant and its license.

---

## 5. Rejected delivery options

| Option | Why not |
| :--- | :--- |
| Download official binaries from pngquant.org or GitHub Releases, with pinned sha256 | A URL and hash per platform to maintain; pngquant.org only has an unversioned `pngquant.tar.bz2`, so a pinned hash breaks on every upstream release, and the macOS build's architecture is undocumented. |
| Use whatever is on `PATH` | Versions differ between machines. |
| `mise use -g` plus shims | Changes the user's global config; shims follow the current folder's config. |
| Download the conda-forge binary alone | It is dynamically linked against other conda packages and does not run on its own. |
| `pngquant-cli` and `pyoxipng` wheels (pure `uvx`, no system dependency) | Third-party packaging; the user prefers official binaries managed by mise, and only local Macs are targeted. |
