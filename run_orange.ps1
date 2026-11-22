# 개발용: 소스 체크아웃의 브리지로 Orange 를 직접 띄운다 (배포판은 mcp_orange.exe 가 launch_orange 로 띄움).
# 배포 폴더(%LOCALAPPDATA%\mcp_orange\bridge)로 브리지를 복사해 같은 방식으로 실행한다.
param([string]$OrangePython = "")
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = if ($OrangePython) { $OrangePython } elseif ($env:ORANGE_PYTHON) { $env:ORANGE_PYTHON } else { "$root\..\Orange\python.exe" }
$deploy = & "$root\.venv\Scripts\python.exe" -B -c "import sys; sys.path.insert(0, r'$root'); from mcp_orange_app import launcher; print(launcher.deploy_bridge())"
$env:PYTHONPATH = $deploy
Set-Location $deploy
& $py -s -B -m orange_mcp_bridge -l4 @args
