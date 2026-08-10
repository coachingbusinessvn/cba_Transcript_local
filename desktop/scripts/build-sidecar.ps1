# Build ViTranscript Python sidecar (PyInstaller). ASCII-only.
# Usage: .\desktop\scripts\build-sidecar.ps1 [-Mode onefile|onedir|both]
param(
    [ValidateSet("onefile", "onedir", "both")]
    [string]$Mode = "both"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "==> uv sync --frozen --group desktop"
uv sync --frozen --group desktop

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

Write-Host "==> resolve ffmpeg/ffprobe"
$resolve = uv run python -c @"
import json, hashlib, platform, sys
from pathlib import Path
import static_ffmpeg.run as sfr
ff, fp = sfr.get_or_fetch_platform_executables_else_raise()
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda: f.read(1<<20), b''):
            h.update(c)
    return h.hexdigest()
meta={
  'ffmpeg_path': ff, 'ffprobe_path': fp,
  'ffmpeg_sha256': sha(ff), 'ffprobe_sha256': sha(fp),
  'os': platform.system(), 'arch': platform.machine(),
  'python': sys.version.split()[0],
}
Path('desktop/pyinstaller').mkdir(parents=True, exist_ok=True)
Path('desktop/pyinstaller/_ffmpeg_resolve.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
print(ff)
print(fp)
"@
$lines = $resolve -split "`n" | Where-Object { $_.Trim() -ne "" }
$env:VITRANSCRIPT_BUNDLE_FFMPEG = $lines[0].Trim()
$env:VITRANSCRIPT_BUNDLE_FFPROBE = $lines[1].Trim()

$Spec = "desktop/pyinstaller/vitranscript-sidecar.spec"
$Dist = "desktop/pyinstaller/dist"
$Build = "desktop/pyinstaller/build"
New-Item -ItemType Directory -Force -Path $Dist, $Build | Out-Null

function Build-Mode([string]$m) {
    Write-Host "==> PyInstaller mode=$m"
    uv run pyinstaller --clean --noconfirm --distpath $Dist --workpath "$Build/$m" $Spec -- --mode $m
}

if ($Mode -eq "onedir" -or $Mode -eq "both") {
    Build-Mode "onedir"
    $bin = Join-Path $Dist "vitranscript-sidecar\vitranscript-sidecar.exe"
    if (Test-Path $bin) { & $bin --self-test-native }
}
if ($Mode -eq "onefile" -or $Mode -eq "both") {
    Build-Mode "onefile"
    $bin = Join-Path $Dist "vitranscript-sidecar.exe"
    if (Test-Path $bin) { & $bin --self-test-native }
}

Write-Host "==> build-sidecar done (mode=$Mode)"
