# Build Windows desktop (NSIS). ASCII-only. Native x64 only.
param()
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

function Assert-LastExitCode([string]$Step) {
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "FAILED: $Step (exit=$LASTEXITCODE)"
    }
}

$env:Path = "$env:USERPROFILE\.cargo\bin;$env:USERPROFILE\.local\bin;$env:Path"

$Triple = (rustc --print host-tuple).Trim()
Write-Host "host triple: $Triple"

# Python arch vs rustc triple (fail before stage).
$PyMachine = (uv run python -c "import platform; print(platform.machine())").Trim()
Assert-LastExitCode "python platform.machine"
$Expect = switch -Regex ($PyMachine) {
    '^(AMD64|x86_64|x64)$' { "x86_64-pc-windows-msvc" }
    '^(ARM64|aarch64)$' { "aarch64-pc-windows-msvc" }
    default { throw "unsupported Python machine=$PyMachine" }
}
if ($Triple -ne $Expect) {
    throw "rustc triple ($Triple) != Python arch triple ($Expect from machine=$PyMachine)"
}

Write-Host "==> sidecar (onefile)"
& powershell -File "desktop\scripts\build-sidecar.ps1" -Mode onefile
Assert-LastExitCode "build-sidecar.ps1"

$SidecarSrc = "desktop\pyinstaller\dist\vitranscript-sidecar.exe"
if (-not (Test-Path $SidecarSrc)) {
    throw "missing $SidecarSrc"
}

# PE machine type (0x8664 = AMD64) via Python struct — no external deps.
uv run python -c @"
import struct, sys
from pathlib import Path
p = Path(r'$SidecarSrc')
data = p.read_bytes()
if data[:2] != b'MZ':
    print('ERROR: not a PE (no MZ)'); sys.exit(1)
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
if data[e_lfanew:e_lfanew+4] != b'PE\0\0':
    print('ERROR: bad PE signature'); sys.exit(1)
machine = struct.unpack_from('<H', data, e_lfanew + 4)[0]
# IMAGE_FILE_MACHINE_AMD64 = 0x8664; ARM64 = 0xAA64
triple = r'$Triple'
if triple.startswith('x86_64') and machine != 0x8664:
    print(f'ERROR: PE machine=0x{machine:04X} expected AMD64 for {triple}'); sys.exit(1)
if 'aarch64' in triple and machine != 0xAA64:
    print(f'ERROR: PE machine=0x{machine:04X} expected ARM64 for {triple}'); sys.exit(1)
print(f'OK PE machine=0x{machine:04X} matches {triple}')
"@
Assert-LastExitCode "PE machine check"

$SrcHash = (Get-FileHash -Algorithm SHA256 $SidecarSrc).Hash.ToLower()

$StageDir = "desktop\src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
$Staged = Join-Path $StageDir "vitranscript-sidecar-$Triple.exe"
Get-ChildItem $StageDir -Filter "vitranscript-sidecar-*" -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item -Force $SidecarSrc $Staged
$StHash = (Get-FileHash -Algorithm SHA256 $Staged).Hash.ToLower()
if ($SrcHash -ne $StHash) { throw "staged checksum mismatch" }
Write-Host "staged $Staged sha256=$StHash"

if (-not (Test-Path "desktop\pyinstaller\dist\sidecar-manifest.json")) {
    throw "missing sidecar-manifest.json (build-sidecar must write it)"
}

Write-Host "==> cargo tauri build (windows)"
# Tauri CLI 2.x does not accept cargo's --manifest-path; run from src-tauri.
Push-Location "desktop\src-tauri"
try {
    cargo tauri build --no-sign --config tauri.windows.conf.json
    Assert-LastExitCode "cargo tauri build"
}
finally {
    Pop-Location
}

Write-Host "==> artifacts"
Get-ChildItem -Recurse "desktop\src-tauri\target\release\bundle" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $h = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower()
    Write-Host "$h  $($_.FullName)"
}
Write-Host "build-windows done"
