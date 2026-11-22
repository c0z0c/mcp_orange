# mcp_orange.exe 를 빌드한다.
#   build\build_exe.ps1            -> dist\mcp_orange.exe
# 빌드 전용 venv(build\.venv)를 쓴다. 없으면 만든다 (Python 3.12 이상 권장).
param([string]$Python = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$venv = Join-Path $here ".venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    $py = if ($Python) { $Python } else { "python" }
    & $py -m venv $venv
    & "$venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r "$root\relay\requirements.txt" pyinstaller
}
Push-Location $root
try {
    & "$venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean `
        --distpath "$root\dist" --workpath "$here\work" "$here\mcp_orange.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
} finally {
    Pop-Location
    # 빌드가 굳힌 버전 파일이 소스 실행(개발 모드)의 버전 계산을 가리지 않도록 지운다
    Remove-Item "$root\mcp_orange_app\_buildinfo.py" -ErrorAction SilentlyContinue
}
$exe = "$root\dist\mcp_orange.exe"
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
"$hash  mcp_orange.exe" | Set-Content -Encoding ascii "$root\dist\SHA256SUMS.txt"
$vi = (Get-Item $exe).VersionInfo
"version  $($vi.FileVersion)  (product: $($vi.ProductVersion))"
"{0}  {1:N1} MB" -f $exe, ((Get-Item $exe).Length / 1MB)
"sha256 $hash"
