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

Write-Host "==> resolve ffmpeg/ffprobe + license audit"
uv run python -c @"
import json, hashlib, platform, re, subprocess, sys
from pathlib import Path
import static_ffmpeg.run as sfr

ff, fp = sfr.get_or_fetch_platform_executables_else_raise()

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda: f.read(1<<20), b''):
            h.update(c)
    return h.hexdigest()

def audit_ffmpeg(path):
    try:
        proc = subprocess.run([path, '-version'], capture_output=True, text=True, timeout=30, check=False)
    except OSError as e:
        print('ERROR cannot execute ffmpeg:', e); sys.exit(1)
    text = (proc.stdout or '') + '\n' + (proc.stderr or '')
    if 'ffmpeg version' not in text.lower() and 'version' not in text.lower():
        print('ERROR ffmpeg -version failed', proc.returncode); sys.exit(1)
    version_line = ''
    configuration = ''
    for line in text.splitlines():
        ls = line.strip()
        if not version_line and ls.lower().startswith('ffmpeg version'):
            version_line = ls
        if ls.lower().startswith('configuration:'):
            configuration = ls.split(':', 1)[1].strip() if ':' in ls else ls
    if not version_line:
        print('ERROR no version line'); sys.exit(1)
    if not configuration:
        print('ERROR no configuration line — cannot audit license'); sys.exit(1)
    cfg_l = configuration.lower()
    if re.search(r'--enable-nonfree\b', cfg_l):
        print('ERROR NONFREE ffmpeg'); sys.exit(1)
    if re.search(r'--enable-gpl\b', cfg_l) and not re.search(r'--disable-gpl\b', cfg_l):
        license_kind = 'GPL'
    else:
        license_kind = 'LGPL'
    return version_line, configuration, license_kind

ver, cfg, lic = audit_ffmpeg(ff)
meta = {
  'ffmpeg_basename': Path(ff).name,
  'ffprobe_basename': Path(fp).name,
  'ffmpeg_path': ff,
  'ffprobe_path': fp,
  'ffmpeg_sha256': sha(ff),
  'ffprobe_sha256': sha(fp),
  'ffmpeg_version_line': ver,
  'ffmpeg_configuration': cfg,
  'ffmpeg_license': lic,
  'source_package': 'static-ffmpeg (PyPI)',
  'os': platform.system(),
  'arch': platform.machine(),
  'python': sys.version.split()[0],
}
Path('desktop/pyinstaller').mkdir(parents=True, exist_ok=True)
Path('desktop/pyinstaller/_ffmpeg_resolve.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
Path('desktop/pyinstaller/_ffmpeg.path').write_text(ff, encoding='utf-8')
Path('desktop/pyinstaller/_ffprobe.path').write_text(fp, encoding='utf-8')
print(ff)
print(fp)
print('LICENSE', lic)
"@
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

Write-Host "==> write sidecar-manifest.json"
uv run python -c @"
import hashlib, json, platform, sys
from pathlib import Path
from datetime import datetime, timezone

root = Path('.')
dist = root / 'desktop/pyinstaller/dist'
onefile = dist / 'vitranscript-sidecar.exe'
onedir = dist / 'vitranscript-sidecar' / 'vitranscript-sidecar.exe'
p = root / 'desktop/pyinstaller/_ffmpeg_resolve.json'
if not p.is_file():
    print('ERROR missing _ffmpeg_resolve.json'); sys.exit(1)
ff_meta = json.loads(p.read_text(encoding='utf-8'))
if not ff_meta.get('ffmpeg_license') or not ff_meta.get('ffmpeg_version_line') or not ff_meta.get('ffmpeg_configuration'):
    print('ERROR incomplete ffmpeg audit'); sys.exit(1)

def sha(path: Path):
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return {'name': path.name, 'size': path.stat().st_size, 'sha256': h.hexdigest()}

ff_public = {
    'ffmpeg_basename': ff_meta.get('ffmpeg_basename'),
    'ffprobe_basename': ff_meta.get('ffprobe_basename'),
    'ffmpeg_sha256': ff_meta.get('ffmpeg_sha256'),
    'ffprobe_sha256': ff_meta.get('ffprobe_sha256'),
    'ffmpeg_version_line': ff_meta.get('ffmpeg_version_line'),
    'ffmpeg_configuration': ff_meta.get('ffmpeg_configuration'),
    'ffmpeg_license': ff_meta.get('ffmpeg_license'),
    'source_package': ff_meta.get('source_package', 'static-ffmpeg (PyPI)'),
}
manifest = {
    'created_at': datetime.now(timezone.utc).isoformat(),
    'os': platform.system(),
    'arch': platform.machine(),
    'python': sys.version.split()[0],
    'ffmpeg': ff_public,
    'onefile': sha(onefile) if onefile.is_file() else None,
    'onedir': sha(onedir) if onedir.is_file() else None,
}
out = dist / 'sidecar-manifest.json'
out.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Wrote', out)
"@
Assert-LastExitCode "sidecar-manifest.json"

if (-not (Test-Path "desktop\pyinstaller\dist\sidecar-manifest.json")) {
    throw "sidecar-manifest.json was not created"
}

Write-Host "==> build-sidecar done (mode=$Mode)"
