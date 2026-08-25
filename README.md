# APS — AI Project Standard CLI

APS installs and operates the AI Project Standard inside new or existing software projects.

## Publish this repository once

After creating a GitHub repository, bind the distribution files to it:

```bash
python scripts/configure_repository.py OWNER/REPO
git add .
git commit -m "Configure APS distribution"
git push
```

Then tag a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions builds `APS_CLI_1.0.0.zip` and its SHA-256 file and attaches them to the Release.

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
aps rebaseline
aps doctor
aps status
aps upgrade
```

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
