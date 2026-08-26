# APS — AI Project Standard CLI

APS installs and operates the AI Project Standard inside new or existing software projects.

## Publish this repository once

After creating a GitHub repository, bind the distribution files to it:

```bash
python scripts/configure_repository.py OWNER/REPO
git status --short
# Review the changed paths, then stage only the files intended for release.
git add -- <reviewed-files>
git diff --cached --check
git commit -m "Configure APS distribution"
git push
```

Then tag a release:

```bash
git tag v1.2.0
git push origin v1.2.0
```

When changing files under `src/aps_cli/bundle/package/`, refresh their manifest checksums before committing:

```bash
python scripts/build_release.py --refresh-manifest
```

GitHub Actions builds `APS_CLI_1.2.0.zip` and its SHA-256 file and attaches them to the Release.
The online installers verify that SHA-256 file and fail closed when no verified Release asset is available.

## One-line install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/meiyisiaaa/aps-dev-standard/main/install.sh | sh
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/meiyisiaaa/aps-dev-standard/main/install.ps1 | iex
```

After installation:

```bash
cd your-project
aps
```

Or directly:

```bash
aps init
aps resume
aps rebaseline --confirm
aps doctor
aps status
aps upgrade
aps research brief .ai/cycles/CYCLE-001/stages/02-market-research/02_MARKET_RESEARCH.md
```

Command boundaries are deliberate: `init` is for a new project, `resume` adopts an existing project once and is read-only after a valid Standard manifest exists, and `upgrade` is the only normal command that updates installed Standard files. `rebaseline` requires initialized runtime state and explicit confirmation; an incomplete non-initial Cycle must be resumed before another one is created:

```bash
aps rebaseline --confirm
```

Repeating `resume` or a same-version `upgrade` is a no-op and should not dirty the project workspace. Do not use `init --force-mode` to bypass an existing project; use `resume` to adopt it.

When a major product, technical, UX, or scope choice is required, create a structured Decision Request under the active Cycle and register it:

```bash
aps decision request .ai/cycles/CYCLE-001/stages/01-idea/decision-requests/DEC-001.json
```

In Codex Plan mode, use the native user-input prompt for the current smallest question. Keep the full candidate set in the Decision Request; multi-select, ranking, free-text, numeric, and larger decisions may use staged prompts or conversation fallback. Record the answer with:

```bash
aps decision answer DEC-001 A
```

Use `aps decision list` and `aps decision show DEC-001` to inspect pending requests. A selected option does not pass a Gate automatically; complete the required Artifact and Validation first.

If the request is no longer needed, close it explicitly:

```bash
aps decision cancel DEC-001 --reason "scope changed"
```

After switching conversations, run `aps status` or `aps resume --no-launch` to print the current Cycle, blockers, pending decisions, and next action. For Market / Product Research, keep the full report in the Stage Artifact and expose the user-facing summary with `aps research brief <ARTIFACT>`.

## Temporary use before repository configuration

The installers also accept a repository override.

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | APS_REPO=OWNER/REPO sh
```

PowerShell:

```powershell
$env:APS_REPO='OWNER/REPO'; irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
```

For temporary source-archive use when no Release exists, explicitly opt in:

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | APS_REPO=OWNER/REPO APS_ALLOW_MAIN_FALLBACK=1 sh
```

PowerShell:

```powershell
$env:APS_REPO='OWNER/REPO'; $env:APS_ALLOW_MAIN_FALLBACK='1'; irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
```

## Project footprint

APS keeps project governance isolated:

```text
project/
├── AGENTS.md
├── .agents/
│   └── skills/
└── .ai/
    ├── standards/
    ├── bootstrap/
    ├── tools/
    ├── schemas/
    ├── runtime/
    ├── cycles/
    └── archive/
```

The product source tree stays separate from AI governance assets.
