param([string]$Repository = 'user-cj/daily-ai-radio')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$taskRoot = [IO.Path]::GetFullPath($PSScriptRoot)
Set-Location -LiteralPath $taskRoot
$taskState = Join-Path $taskRoot 'work/publish'
New-Item -ItemType Directory -Path $taskState -Force | Out-Null
$taskGitCommand = Get-Command git -ErrorAction SilentlyContinue
$taskBundledGit = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'
if ($taskGitCommand) { $taskGit = $taskGitCommand.Source }
elseif (Test-Path -LiteralPath $taskBundledGit) { $taskGit = $taskBundledGit }
else { throw '需要安装 Git for Windows 后重新运行。' }
$taskGhCommand = Get-Command gh -ErrorAction SilentlyContinue
$taskExistingGh = [IO.Path]::GetFullPath((Join-Path $taskRoot '../../work/tools/gh/bin/gh.exe'))
if ($taskGhCommand) { $taskGh = $taskGhCommand.Source }
elseif (Test-Path -LiteralPath $taskExistingGh) { $taskGh = $taskExistingGh }
else {
    Write-Host '下载 GitHub 官方登录工具；不需要付费 API。'
    $taskToolDir = Join-Path $taskState 'tools'
    $taskArchive = Join-Path $taskState 'gh.zip'
    New-Item -ItemType Directory -Path $taskToolDir -Force | Out-Null
    Invoke-WebRequest -Uri 'https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_windows_amd64.zip' -OutFile $taskArchive -UseBasicParsing -TimeoutSec 180
    Expand-Archive -LiteralPath $taskArchive -DestinationPath $taskToolDir -Force
    $taskGh = (Get-ChildItem -LiteralPath $taskToolDir -Recurse -Filter gh.exe | Select-Object -First 1).FullName
}
function Invoke-TaskGit {
    param([string[]]$Arguments)
    & $taskGit @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Git 操作失败：' + ($Arguments -join ' ')) }
}
function Invoke-TaskGh {
    param([string[]]$Arguments)
    $taskResult = & $taskGh @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('GitHub 操作失败：' + ($Arguments -join ' ')) }
    return $taskResult
}
Write-Host '核对 GitHub 登录状态。'
& $taskGh auth status --hostname github.com 2> (Join-Path $taskState 'auth-check.log')
if ($LASTEXITCODE -ne 0) {
    Write-Host '请在 GitHub 官方网页完成本次账号连接；不要把密码或令牌发给聊天。'
    Invoke-TaskGh -Arguments @('auth','login','--hostname','github.com','--git-protocol','https','--web','--skip-ssh-key','--scopes','workflow')
}
Invoke-TaskGh -Arguments @('auth','setup-git','--hostname','github.com')
$taskRepo = (Invoke-TaskGh -Arguments @('api',('repos/' + $Repository))) | ConvertFrom-Json
if (-not $taskRepo.permissions.push -or -not $taskRepo.permissions.admin) { throw '当前登录账号缺少目标仓库的上传或 Pages 管理权限。请连接仓库所有者账号。' }
if ($taskRepo.default_branch -ne 'main') { throw '远程默认分支不是 main，需先核对分支配置。' }
$taskActor = (Invoke-TaskGh -Arguments @('api','user')) | ConvertFrom-Json
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot '.git'))) {
    Invoke-TaskGit -Arguments @('init','--initial-branch=main')
    Invoke-TaskGit -Arguments @('remote','add','origin',('https://github.com/' + $Repository + '.git'))
    Invoke-TaskGit -Arguments @('fetch','origin','main')
    $taskOriginalBase = (Get-Content -LiteralPath (Join-Path $taskRoot 'repo-base.txt') -Raw).Trim()
    if ($taskOriginalBase -notmatch '^[a-f0-9]{40}$') { throw '交付包缺少可信的原始仓库版本记录。' }
    Invoke-TaskGit -Arguments @('cat-file','-e',($taskOriginalBase + '^{commit}'))
    Invoke-TaskGit -Arguments @('update-ref','refs/heads/main',$taskOriginalBase)
}
$taskOrigin = (Invoke-TaskGit -Arguments @('remote','get-url','origin')).Trim()
if ($taskOrigin -notin @(('https://github.com/' + $Repository + '.git'),('https://github.com/' + $Repository))) { throw '当前目录连接到不同仓库，已停止上传。' }
$taskBranch = (Invoke-TaskGit -Arguments @('branch','--show-current')).Trim()
if ($taskBranch -ne 'main') { throw '当前目录不在 main 分支，已停止上传。' }
Invoke-TaskGit -Arguments @('config','user.name',$taskActor.login)
Invoke-TaskGit -Arguments @('config','user.email',($taskActor.id.ToString() + '+' + $taskActor.login + '@users.noreply.github.com'))
Invoke-TaskGit -Arguments @('add','--all')
& $taskGit diff --cached --quiet
if ($LASTEXITCODE -eq 1) { Invoke-TaskGit -Arguments @('commit','-m','Initialize daily AI radio with verified first edition') }
elseif ($LASTEXITCODE -ne 0) { throw '无法核对待上传文件。' }
Invoke-TaskGit -Arguments @('pull','--rebase','origin','main')
Invoke-TaskGit -Arguments @('push','origin','main')
Write-Host '启用 GitHub Pages，通过 Actions 发布。'
$taskPages = & $taskGh api ('repos/' + $Repository + '/pages') 2> (Join-Path $taskState 'pages-check.log')
$taskPagesExists = $LASTEXITCODE -eq 0
$taskPagesBody = Join-Path $taskState 'pages.json'
[IO.File]::WriteAllText($taskPagesBody, '{"build_type":"workflow"}', (New-Object Text.UTF8Encoding($false)))
$taskPagesMethod = if ($taskPagesExists) { 'PUT' } else { 'POST' }
Invoke-TaskGh -Arguments @('api',('repos/' + $Repository + '/pages'),'--method',$taskPagesMethod,'--input',$taskPagesBody) | Out-Null
Write-Host '手动运行第一期云端发布。'
Invoke-TaskGh -Arguments @('workflow','run','daily-radio.yml','--repo',$Repository,'--ref','main')
$taskRunId = $null
for ($taskAttempt=0; $taskAttempt -lt 15; $taskAttempt++) {
    Start-Sleep -Seconds 3
    $taskRuns = (Invoke-TaskGh -Arguments @('run','list','--repo',$Repository,'--workflow','daily-radio.yml','--event','workflow_dispatch','--limit','1','--json','databaseId,status,conclusion')) | ConvertFrom-Json
    if ($taskRuns.Count -gt 0) { $taskRunId=$taskRuns[0].databaseId.ToString(); break }
}
if (-not $taskRunId) { throw '未找到手动运行记录，请查看仓库 Actions 页面。' }
Write-Host ('等待云端运行：' + $taskRunId)
Invoke-TaskGh -Arguments @('run','watch',$taskRunId,'--repo',$Repository,'--exit-status')
$taskPages = (Invoke-TaskGh -Arguments @('api',('repos/' + $Repository + '/pages'))) | ConvertFrom-Json
$taskUrl = $taskPages.html_url
if (-not $taskUrl) { throw '云端部署后仍未返回电台网址。' }
$taskWebResult = Invoke-WebRequest -Uri $taskUrl -UseBasicParsing -TimeoutSec 45
if ($taskWebResult.StatusCode -ne 200 -or $taskWebResult.Content -notmatch 'AI') { throw '电台网页未通过公开访问检查。' }
[IO.File]::WriteAllText((Join-Path $taskRoot '电台网址.txt'), $taskUrl, (New-Object Text.UTF8Encoding($false)))
Write-Host ('电台已发布：' + $taskUrl)
Write-Host '在 iPhone Safari 打开这个地址，点击播放；随后检查锁屏播放，并添加到主屏幕。'
