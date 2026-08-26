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

$python = Get-Command py -ErrorAction SilentlyContinue
$pythonArgs = @()
if ($python) {
    $pythonExe = $python.Source
    $pythonArgs = @("-3")
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw "Python 3 is required." }
    $pythonExe = $python.Source
}

function Test-ReleaseChecksum {
    param(
        [Parameter(Mandatory=$true)][string]$AssetPath,
        [Parameter(Mandatory=$true)][string]$ChecksumPath
    )
    $line = Get-Content -LiteralPath $ChecksumPath | Where-Object { $_.Trim() } | Select-Object -First 1
    $match = [regex]::Match($line, '^\s*([0-9a-fA-F]{64})\s+\S+\s*$')
    if (-not $match.Success) { throw "Invalid SHA-256 sidecar." }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $AssetPath).Hash
    if (-not $actual.Equals($match.Groups[1].Value, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Release SHA-256 mismatch."
    }
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ("aps-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $asset = Join-Path $tmp "aps.zip"
    $checksum = Join-Path $tmp "aps.zip.sha256"
    $downloaded = $false
    $tag = ""
    if ($Version -eq "latest") {
        try {
            $release = Invoke-RestMethod -Headers @{"User-Agent"="aps-installer"} -Uri "https://api.github.com/repos/$Repo/releases/latest"
            $tag = $release.tag_name
        } catch { $tag = "" }
    } else { $tag = $Version }
    if ($tag -and $tag -notmatch '^v') { $tag = "v$tag" }

    if ($tag) {
        $normalized = $tag.TrimStart("v")
        $url = "https://github.com/$Repo/releases/download/$tag/APS_CLI_$normalized.zip"
        try {
            Invoke-WebRequest -Headers @{"User-Agent"="aps-installer"} -Uri $url -OutFile $asset
        } catch { $downloaded = $false }
        if (Test-Path -LiteralPath $asset) {
            try {
                Invoke-WebRequest -Headers @{"User-Agent"="aps-installer"} -Uri "$url.sha256" -OutFile $checksum
                Test-ReleaseChecksum -AssetPath $asset -ChecksumPath $checksum
                $downloaded = $true
            } catch {
                throw "Release asset verification failed: $($_.Exception.Message)"
            }
        }
    }
    if (-not $downloaded) {
        if ($env:APS_ALLOW_MAIN_FALLBACK -ne "1") {
            throw "No verified release asset is available. Set APS_ALLOW_MAIN_FALLBACK=1 to use the mutable main branch explicitly."
        }
        Write-Host "No verified release asset; explicitly using the mutable main branch source archive."
        Invoke-WebRequest -Headers @{"User-Agent"="aps-installer"} -Uri "https://github.com/$Repo/archive/refs/heads/main.zip" -OutFile $asset
    }
    $extract = Join-Path $tmp "extract"
    Expand-Archive -LiteralPath $asset -DestinationPath $extract -Force
    $installer = Get-ChildItem -Path $extract -Filter install_cli.py -Recurse | Sort-Object { $_.FullName.Split([IO.Path]::DirectorySeparatorChar).Count } | Select-Object -First 1
    if (-not $installer) { throw "install_cli.py not found in downloaded archive." }
    $argsList = @($pythonArgs) + @($installer.FullName)
    if ($Prefix) { $argsList += @("--prefix", $Prefix) }
    & $pythonExe @argsList
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
