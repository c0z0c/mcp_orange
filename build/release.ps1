# 릴리스: README 히스토리 갱신 -> 커밋 -> exe 빌드 -> 태그 -> push -> GitHub Release
#   build\release.ps1 -DryRun    계획만 출력 (아무것도 바꾸지 않음)
#   build\release.ps1            확인 후 실행   (-Yes 로 확인 생략)
# 사전 조건: master 브랜치, 작업 트리 clean, gh CLI 로그인
# 버전   = version.txt + (현재 커밋 수 + 1)   ← 이 스크립트가 만드는 릴리스 커밋이 +1
# 변경 내용 = 마지막 태그 이후 커밋 제목 ("Release " 로 시작하는 것 제외)
param([switch]$DryRun, [switch]$Yes)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

# ---- 사전 점검
if ((git branch --show-current) -ne "master") { throw "master 브랜치에서만 릴리스합니다." }
if (git status --porcelain) {
    if ($DryRun) { Write-Warning "작업 트리에 미커밋 변경이 있습니다 (실제 릴리스는 거부됩니다)." }
    else { throw "미커밋 변경이 있습니다. 먼저 커밋하세요." }
}
if (-not $DryRun) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "gh CLI 가 필요합니다 (https://cli.github.com)." }
    gh auth status *> $null
    if ($LASTEXITCODE) { throw "gh 로그인이 필요합니다: gh auth login" }
}

# ---- 버전·변경 내용 계산
$base    = ((Get-Content version.txt -TotalCount 1) -replace "^﻿", "").Trim()
$next    = "{0}.{1}" -f $base, ([int](git rev-list --count HEAD) + 1)
$tag     = "v$next"
$lastTag = git tag --list "v*" --sort=-v:refname | Select-Object -First 1
$range   = if ($lastTag) { "$lastTag..HEAD" } else { "HEAD" }
$changes = @(git log --pretty=%s $range | Where-Object { $_ -and $_ -notmatch "^Release " })
if (-not $changes) { throw "마지막 태그($lastTag) 이후 새 커밋이 없습니다." }
$notes = ($changes | ForEach-Object { "- $_" }) -join "`n"
$row   = "| {0} | {1} | {2} |" -f $next, (Get-Date -Format "yyyy-MM-dd"), (($changes -join " / ") -replace "\|", "/")

"버전 : $next  (태그 $tag, 이전 태그: $(if ($lastTag) { $lastTag } else { '없음' }))"
"변경 :`n$notes"
"README 히스토리 추가: $row"
if ($DryRun) { "`n[DryRun] 변경 없이 종료"; return }
if (-not $Yes -and (Read-Host "`n위 내용으로 커밋·빌드·push·릴리스를 진행할까요? (y/N)") -ne "y") { "취소"; return }

# ---- README 히스토리(표의 맨 위) 갱신 -> 릴리스 커밋
$utf8 = New-Object Text.UTF8Encoding $false
$lines = [System.Collections.Generic.List[string]]([IO.File]::ReadAllLines("$root\README.md", $utf8))
$head = $lines.IndexOf("## 버전 히스토리")
if ($head -lt 0) { throw "README.md 에 '## 버전 히스토리' 절이 없습니다." }
$sep = $head
while ($sep -lt $lines.Count -and $lines[$sep] -ne "|---|---|---|") { $sep++ }
if ($sep -ge $lines.Count) { throw "README.md 히스토리 표(|---|---|---|)를 찾지 못했습니다." }
$lines.Insert($sep + 1, $row)
[IO.File]::WriteAllLines("$root\README.md", $lines, $utf8)
git add README.md
git commit -q -m "Release $tag" -m $notes
if ($LASTEXITCODE) { throw "커밋 실패" }

# ---- 빌드 (커밋 수가 $next 와 일치해야 함)
& "$root\build\build_exe.ps1"
$built = (Get-Item "$root\dist\mcp_orange.exe").VersionInfo.FileVersion
if ($built -ne $next) { throw "exe 버전($built) != 예상($next). 'git reset --soft HEAD~1' 로 릴리스 커밋을 되돌리고 확인하세요." }

# ---- 태그, push, GitHub Release
git tag $tag
git push origin master
git push origin $tag
$sha = (Get-Content "$root\dist\SHA256SUMS.txt" -Raw).Trim()
gh release create $tag "$root\dist\mcp_orange.exe" "$root\dist\SHA256SUMS.txt" `
    --title "mcp_orange $next" --notes "$notes`n`nSHA256:`n$sha"
if ($LASTEXITCODE) { throw "GitHub Release 생성 실패 (태그는 push 됨: gh release create $tag ...)" }
"완료: https://github.com/c0z0c/mcp_orange/releases/tag/$tag"
