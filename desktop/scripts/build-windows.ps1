# Build Windows desktop (NSIS). ASCII-only. Native x64 only.
param()
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$env:Path = "$env:USERPROFILE\.cargo\bin;$env:USERPROFILE\.local\bin;$env:Path"

$Triple = (rustc --print host-tuple).Trim()
Write-Host "host triple: $Triple"

Write-Host "==> sidecar (onefile)"
& powershell -File "desktop\scripts\build-sidecar.ps1" -Mode onefile

$SidecarSrc = "desktop\pyinstaller\dist\vitranscript-sidecar.exe"
if (-not (Test-Path $SidecarSrc)) {
    throw "missing $SidecarSrc"
}
$SrcHash = (Get-FileHash -Algorithm SHA256 $SidecarSrc).Hash.ToLower()

$StageDir = "desktop\src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
$Staged = Join-Path $StageDir "vitranscript-sidecar-$Triple.exe"
Get-ChildItem $StageDir -Filter "vitranscript-sidecar-*" -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item -Force $SidecarSrc $Staged
$StHash = (Get-FileHash -Algorithm SHA256 $Staged).Hash.ToLower()
if ($SrcHash -ne $StHash) { throw "staged checksum mismatch" }
Write-Host "staged $Staged sha256=$StHash"

Write-Host "==> cargo tauri build (windows)"
cargo tauri build --manifest-path desktop/src-tauri/Cargo.toml `
  --no-sign `
  --config desktop/src-tauri/tauri.windows.conf.json

Write-Host "==> artifacts"
Get-ChildItem -Recurse "desktop\src-tauri\target\release\bundle" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $h = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower()
    Write-Host "$h  $($_.FullName)"
}
Write-Host "build-windows done"
