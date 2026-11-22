# Restart Orange (debug bridge) and run the whole regression suite.
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = "$root\.venv\Scripts\python.exe"
& "$root\scripts\restart.ps1" -Debug | Select-Object -Last 1
$tests = 'scenario_iris', 'test_controls', 'test_select', 'test_docs', 'test_dialog', 'test_autodismiss', 'test_relay', 'test_manage', 'test_app'
$bad = @()
foreach ($t in $tests) {
    $out = & $py "$root\tests\$t.py" 2>&1 | Out-String
    $fail = ($out -split "`n" | Where-Object { $_ -match '^FAIL ' })
    $pass = ($out -split "`n" | Where-Object { $_ -match '^PASS ' }).Count
    if ($LASTEXITCODE -ne 0 -or $fail) { $bad += $t; "{0,-18} FAILED  ({1} pass)`n{2}" -f $t, $pass, ($fail -join "`n") }
    else { "{0,-18} ok      ({1} checks)" -f $t, $pass }
}
if ($bad) { "`nFAILED: $($bad -join ', ')"; exit 1 } else { "`nALL PASSED" }
