# 릴리스: README 히스토리 갱신 -> 커밋 -> exe 빌드 -> 태그 -> push -> GitHub Release
#   build\release.ps1 -Message "변경 요약"   작업 트리 변경 + README 히스토리를 *커밋 하나*로 묶어 릴리스
#   build\release.ps1 -DryRun ...            계획만 출력 (아무것도 바꾸지 않음)
#   build\release.ps1 -Yes ...               확인 생략
# 릴리스 커밋이 따로 남지 않도록 상황에 따라 커밋 방식을 고른다.
#   변경 있음            : 변경 전체 + README 히스토리를 -Message 제목의 커밋 1개로 만든다   (버전 = 커밋 수 + 1)
#   변경 없음, push 전   : 마지막 커밋에 README 히스토리를 합친다(amend)                     (버전 = 커밋 수)
#   변경 없음, push 후   : 예전처럼 "Release vX" 커밋을 따로 만든다 (이미 공개된 커밋은 고치지 않는다) (버전 = 커밋 수 + 1)
# 사전 조건: master 브랜치, gh CLI 로그인
# 변경 내용 = 마지막 태그 이후 커밋 제목 ("Release " 로 시작하는 것 제외) (+ 이번에 만들 커밋의 -Message)
param([switch]$DryRun, [switch]$Yes, [string]$Message = "", [string]$Detail = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

# ---- 사전 점검
if ((git branch --show-current) -ne "master") { throw "master 브랜치에서만 릴리스합니다." }
$dirty = [bool](git status --porcelain)
git fetch -q origin master 2>$null
git merge-base --is-ancestor HEAD origin/master 2>$null
$pushed = ($LASTEXITCODE -eq 0)
$mode = if ($dirty) { "commit" } elseif (-not $pushed) { "amend" } else { "release-commit" }
if ($mode -eq "commit" -and -not $Message.Trim()) {
    if ($DryRun) { Write-Warning "변경이 있으므로 실제 실행에는 -Message 가 필요합니다." }
    else { throw "미커밋 변경이 있습니다. 커밋 제목으로 쓸 -Message ""변경 요약"" 을 주세요." }
}
if (-not $DryRun) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "gh CLI 가 필요합니다 (https://cli.github.com)." }
    gh auth status *> $null
    if ($LASTEXITCODE) { throw "gh 로그인이 필요합니다: gh auth login" }
}

# ---- 버전·변경 내용 계산
$base    = ((Get-Content version.txt -TotalCount 1) -replace "^﻿", "").Trim()
$count   = [int](git rev-list --count HEAD)
$next    = "{0}.{1}" -f $base, $(if ($mode -eq "amend") { $count } else { $count + 1 })
$tag     = "v$next"
$lastTag = git tag --list "v*" --sort=-v:refname | Select-Object -First 1
$range   = if ($lastTag) { "$lastTag..HEAD" } else { "HEAD" }
$changes = @(git log --pretty=%s $range | Where-Object { $_ -and $_ -notmatch "^Release " })
if ($mode -eq "commit" -and $Message.Trim()) { $changes = @($Message.Trim()) + $changes }
if (-not $changes) { throw "마지막 태그($lastTag) 이후 새 커밋이 없습니다." }
$notes = ($changes | ForEach-Object { "- $_" }) -join "`n"
if ($mode -eq "commit" -and $Detail.Trim()) { $notes += "`n`n" + $Detail.Trim() }
$row   = "| {0} | {1} | {2} |" -f $next, (Get-Date -Format "yyyy-MM-dd"), (($changes -join " / ") -replace "\|", "/")

"방식 : $mode " + @{ "commit" = "(변경 전체 + README 히스토리 -> 커밋 1개)"; "amend" = "(마지막 커밋에 README 히스토리 합침, 아직 push 전)";
                      "release-commit" = "(이미 push 된 커밋이라 'Release $tag' 커밋을 따로 만듦)" }[$mode]
if ($mode -eq "commit") { "커밋 대상:"; git status --short }
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
switch ($mode) {
    "commit"         { git add -A
                       $cm = @("-q", "-m", $Message.Trim()); if ($Detail.Trim()) { $cm += @("-m", $Detail.Trim()) }
                       git commit @cm }
    "amend"          { git add README.md; git commit -q --amend --no-edit }
    "release-commit" { git add README.md; git commit -q -m "Release $tag" -m $notes }
}
if ($LASTEXITCODE) { throw "커밋 실패" }

# ---- 빌드 (커밋 수가 $next 와 일치해야 함)
& "$root\build\build_exe.ps1"
$built = (Get-Item "$root\dist\mcp_orange.exe").VersionInfo.FileVersion
if ($built -ne $next) { throw "exe 버전($built) != 예상($next). 아직 push 전이니 'git reset --soft HEAD~1' 로 커밋을 되돌리고 확인하세요 (amend 방식이면 'git reflog' 로 이전 커밋 복구)." }

# ---- 태그, push, GitHub Release
git tag $tag
git push origin master
git push origin $tag
$sha = (Get-Content "$root\dist\SHA256SUMS.txt" -Raw).Trim()
gh release create $tag "$root\dist\mcp_orange.exe" "$root\dist\SHA256SUMS.txt" `
    --title "mcp_orange $next" --notes "$notes`n`nSHA256:`n$sha"
if ($LASTEXITCODE) { throw "GitHub Release 생성 실패 (태그는 push 됨: gh release create $tag ...)" }
"완료: https://github.com/c0z0c/mcp_orange/releases/tag/$tag"
