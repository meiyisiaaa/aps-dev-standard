param(
    [string]$Repo = $env:APS_REPO,
    [string]$Version = $(if ($env:APS_VERSION) { $env:APS_VERSION } else { "latest" }),
    [string]$Prefix = ""
)
$ErrorActionPreference = "Stop"
if (-not $Repo) { $Repo = "meiyisiaaa/aps-dev-standard" }
if ($Repo -notmatch '^[^/]+/[^/]+$') {
    throw "APS installer is not configured. Pass -Repo owner/repo or run scripts/configure_repository.py before publishing."
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { throw "Python 3 is required." }
$pythonExe = $python.Source

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("aps-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $asset = Join-Path $tmp "aps.zip"
    $downloaded = $false
    $tag = ""
    if ($Version -eq "latest") {
        try {
            $release = Invoke-RestMethod -Headers @{"User-Agent"="aps-installer"} -Uri "https://api.github.com/repos/$Repo/releases/latest"
            $tag = $release.tag_name
        } catch { $tag = "" }
    } else { $tag = $Version }

    if ($tag) {
        $normalized = $tag.TrimStart("v")
        $url = "https://github.com/$Repo/releases/download/$tag/APS_CLI_$normalized.zip"
        try {
            Invoke-WebRequest -Headers @{"User-Agent"="aps-installer"} -Uri $url -OutFile $asset
            $downloaded = $true
        } catch { $downloaded = $false }
    }
    if (-not $downloaded) {
        Write-Host "Release asset unavailable; falling back to main branch source archive."
        Invoke-WebRequest -Headers @{"User-Agent"="aps-installer"} -Uri "https://github.com/$Repo/archive/refs/heads/main.zip" -OutFile $asset
    }
    $extract = Join-Path $tmp "extract"
    Expand-Archive -LiteralPath $asset -DestinationPath $extract -Force
    $installer = Get-ChildItem -Path $extract -Filter install_cli.py -Recurse | Sort-Object { $_.FullName.Split([IO.Path]::DirectorySeparatorChar).Count } | Select-Object -First 1
    if (-not $installer) { throw "install_cli.py not found in downloaded archive." }
    $argsList = @($installer.FullName)
    if ($Prefix) { $argsList += @("--prefix", $Prefix) }
    & $pythonExe @argsList
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
