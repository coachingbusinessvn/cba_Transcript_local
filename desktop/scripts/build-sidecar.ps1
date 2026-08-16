# Build ViTranscript Python sidecar (PyInstaller). ASCII-only.
# Usage: .\desktop\scripts\build-sidecar.ps1 [-Mode onefile|onedir|both]
param(
    [ValidateSet("onefile", "onedir", "both")]
    [string]$Mode = "both"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

function Assert-LastExitCode([string]$Step) {
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "FAILED: $Step (exit=$LASTEXITCODE)"
    }
}

Write-Host "==> uv sync --frozen --group desktop"
uv sync --frozen --group desktop
Assert-LastExitCode "uv sync"

Write-Host "==> refuse torch/tensorflow"
uv run python -c @"
import importlib.metadata as m, sys
bad=[]
for d in m.distributions():
    name=(d.metadata.get('Name') or '').lower()
    if name in ('torch','tensorflow','tensorflow-cpu','tensorflow-gpu') or name.startswith('torch-'):
        bad.append(name)
if bad:
    print('ERROR forbidden', bad); sys.exit(1)
print('OK no torch/tensorflow')
"@
Assert-LastExitCode "refuse torch/tensorflow"

Write-Host "==> resolve ffmpeg/ffprobe + license audit (shared Python)"
uv run python desktop/scripts/ffmpeg_license_audit.py resolve
Assert-LastExitCode "ffmpeg resolve/audit"

$ffPath = (Get-Content -Raw "desktop\pyinstaller\_ffmpeg.path").Trim()
$fpPath = (Get-Content -Raw "desktop\pyinstaller\_ffprobe.path").Trim()
if (-not (Test-Path $ffPath)) { throw "ffmpeg path missing: $ffPath" }
if (-not (Test-Path $fpPath)) { throw "ffprobe path missing: $fpPath" }
$env:VITRANSCRIPT_BUNDLE_FFMPEG = $ffPath
$env:VITRANSCRIPT_BUNDLE_FFPROBE = $fpPath
Write-Host "BUNDLE ffmpeg=$ffPath"
Write-Host "BUNDLE ffprobe=$fpPath"

$Spec = "desktop/pyinstaller/vitranscript-sidecar.spec"
$Dist = "desktop/pyinstaller/dist"
$Build = "desktop/pyinstaller/build"
New-Item -ItemType Directory -Force -Path $Dist, $Build | Out-Null

function Audit-WarnFile([string]$WarnPath) {
    if (-not (Test-Path $WarnPath)) { return }
    $pattern = '^missing module named (ctranslate2|onnxruntime|sherpa_onnx|tokenizers|faster_whisper|av|static_ffmpeg)( |$)'
    $hits = Select-String -Path $WarnPath -Pattern $pattern -ErrorAction SilentlyContinue
    if ($hits) {
        Write-Host "ERROR: native module missing in $WarnPath"
        $hits | ForEach-Object { Write-Host $_.Line }
        throw "native module missing (see warn file)"
    }
}

function Build-Mode([string]$m) {
    Write-Host "==> PyInstaller mode=$m"
    $env:VITRANSCRIPT_PYI_MODE = $m
    uv run pyinstaller --clean --noconfirm --distpath $Dist --workpath "$Build/$m" $Spec
    Assert-LastExitCode "pyinstaller $m"
    $warn = Get-ChildItem -Path "$Build\$m" -Filter "warn-*.txt" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($warn) { Audit-WarnFile $warn.FullName }
}

function Run-SelfTest([string]$BinPath) {
    if (-not (Test-Path $BinPath)) {
        throw "sidecar binary missing: $BinPath"
    }
    Write-Host "==> self-test-native: $BinPath"
    & $BinPath --self-test-native
    Assert-LastExitCode "self-test-native $BinPath"
}

if ($Mode -eq "onedir" -or $Mode -eq "both") {
    Build-Mode "onedir"
    $bin = Join-Path $Dist "vitranscript-sidecar\vitranscript-sidecar.exe"
    Run-SelfTest $bin
}
if ($Mode -eq "onefile" -or $Mode -eq "both") {
    Build-Mode "onefile"
    $bin = Join-Path $Dist "vitranscript-sidecar.exe"
    Run-SelfTest $bin
}

Write-Host "==> write sidecar-manifest.json (shared audit + license gate)"
uv run python desktop/scripts/ffmpeg_license_audit.py write-manifest --mode $Mode --dist $Dist
Assert-LastExitCode "sidecar-manifest.json"

if (-not (Test-Path "desktop\pyinstaller\dist\sidecar-manifest.json")) {
    throw "sidecar-manifest.json was not created"
}

Write-Host "==> build-sidecar done (mode=$Mode)"
