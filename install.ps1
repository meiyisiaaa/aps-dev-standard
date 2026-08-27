param(
    [string]$Repo = $env:APS_REPO,
    [string]$Version = $(if ($env:APS_VERSION) { $env:APS_VERSION } else { "latest" }),
    [string]$Prefix = ""
)
$ErrorActionPreference = "Stop"

function Fail-Install {
    param(
        [Parameter(Mandatory=$true)][string]$Message,
        [int]$ExitCode = 1,
        [string]$Next = "检查网络、Python 和权限后重试；若使用源码包，必须显式设置 APS_ALLOW_MAIN_FALLBACK=1。"
    )
    [Console]::Error.WriteLine("FAIL  APS 安装失败：$Message")
    [Console]::Error.WriteLine("原因：Release 校验、下载、解包或本地安装未完成。")
    [Console]::Error.WriteLine("NEXT  $Next")
    exit $ExitCode
}

if (-not $Repo) { $Repo = "meiyisiaaa/aps-dev-standard" }
if ($Repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
    Fail-Install "安装器未配置。请传入 -Repo owner/repo，或先运行 scripts/configure_repository.py。" 2
}

function Test-SafeVersion {
    param([Parameter(Mandatory=$true)][string]$Value)
    return $Value -match '^v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$'
}

if ($Version -ne "latest" -and -not (Test-SafeVersion $Version)) {
    Fail-Install "APS_VERSION 不是安全版本组件：$Version" 2 "使用合法版本，例如 -Version 1.2.2；或保持默认 latest。"
}

$python = Get-Command py -ErrorAction SilentlyContinue
$pythonArgs = @()
if ($python) {
    $pythonExe = $python.Source
    $pythonArgs = @("-3")
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { Fail-Install "需要 Python 3。" 2 }
    $pythonExe = $python.Source
}

function Test-ReleaseChecksum {
    param(
        [Parameter(Mandatory=$true)][string]$AssetPath,
        [Parameter(Mandatory=$true)][string]$ChecksumPath
    )
    $line = Get-Content -LiteralPath $ChecksumPath | Where-Object { $_.Trim() } | Select-Object -First 1
    $match = [regex]::Match($line, '^\s*([0-9a-fA-F]{64})\s+\S+\s*$')
    if (-not $match.Success) { throw "SHA-256 sidecar 格式无效。" }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $AssetPath).Hash
    if (-not $actual.Equals($match.Groups[1].Value, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Release SHA-256 校验不匹配。"
    }
}

function Test-SafeZip {
    param([Parameter(Mandatory=$true)][string]$AssetPath)
    Add-Type -AssemblyName System.IO.Compression
    $zip = [IO.Compression.ZipFile]::OpenRead($AssetPath)
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    try {
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            $key = $name.TrimEnd('/')
            if (-not $key -or $key.StartsWith('/') -or $key -match '^[A-Za-z]:') {
                throw "ZIP 包含绝对或空路径条目：$name"
            }
            if ($name.ToCharArray() | Where-Object { [char]::IsControl($_) }) {
                throw "ZIP 包含控制字符路径：$name"
            }
            foreach ($part in $key.Split('/')) {
                if (-not $part -or $part -eq '.' -or $part -eq '..') {
                    throw "ZIP 包含不安全路径：$name"
                }
            }
            if (-not $seen.Add($key)) {
                throw "ZIP 包含重复或大小写碰撞条目：$name"
            }
            $unixType = (([uint32]$entry.ExternalAttributes -shr 16) -band 0xF000)
            if ($unixType -eq 0xA000) {
                throw "ZIP 包含链接条目：$name"
            }
        }
    } finally {
        $zip.Dispose()
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
    if ($tag -and -not (Test-SafeVersion $tag)) { throw "Release tag 不是安全版本组件：$tag" }

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
                throw "Release 包校验失败：$($_.Exception.Message)"
            }
        }
    }
    if (-not $downloaded) {
        if ($env:APS_ALLOW_MAIN_FALLBACK -ne "1") {
            throw "没有可验证的 Release 包。若明确接受可变 main 源码包，请先设置 APS_ALLOW_MAIN_FALLBACK=1。"
        }
        Write-Host "WARN  没有可验证的 Release 包，已按显式授权使用可变 main 源码包。"
        Invoke-WebRequest -Headers @{"User-Agent"="aps-installer"} -Uri "https://github.com/$Repo/archive/refs/heads/main.zip" -OutFile $asset
    }
    $extract = Join-Path $tmp "extract"
    Test-SafeZip -AssetPath $asset
    Expand-Archive -LiteralPath $asset -DestinationPath $extract -Force
    $installer = Get-ChildItem -Path $extract -Filter install_cli.py -Recurse | Sort-Object { $_.FullName.Split([IO.Path]::DirectorySeparatorChar).Count } | Select-Object -First 1
    if (-not $installer) { throw "下载包中找不到 install_cli.py。" }
    $argsList = @($pythonArgs) + @($installer.FullName)
    if ($Prefix) { $argsList += @("--prefix", $Prefix) }
    & $pythonExe @argsList
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} catch {
    Fail-Install $_.Exception.Message
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
