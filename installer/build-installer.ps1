# 构建 Mac 远控 安装包与便携包
# 用法：pwsh -File build-installer.ps1
#   需要：Inno Setup 6（ISCC.exe）、已打包好的 Mac远控.exe

param(
    [string]$AppExe   = 'C:\Users\Administrator\Desktop\Mac远控\Mac远控.exe',
    [string]$AppDir   = 'C:\Users\Administrator\Desktop\Mac远控',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Version  = '1.0.0'
)

$ErrorActionPreference = 'Stop'
$islcc = (Get-ChildItem -Path 'C:\Program Files (x86)\Inno Setup 6', 'C:\Program Files\Inno Setup 6' `
          -Filter ISCC.exe -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
if (-not $islcc) { throw '没有找到 ISCC.exe，请先安装 Inno Setup 6' }
if (-not (Test-Path -LiteralPath $AppExe)) { throw "找不到主程序：$AppExe" }

# Inno Setup 6 官方安装包不自带简体中文语言文件，缺了就现下（社区翻译，仅在构建期使用）
$langDir = Join-Path (Split-Path -Parent $islcc) 'Languages'
$langFile = Join-Path $langDir 'ChineseSimplified.isl'
if (-not (Test-Path -LiteralPath $langFile)) {
    $url = 'https://raw.githubusercontent.com/kira-96/Inno-Setup-Chinese-Simplified-Translation/master/ChineseSimplified.isl'
    Write-Host "下载简体中文语言文件：$url"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $url -OutFile $langFile -TimeoutSec 60
}

$stage     = Join-Path $PSScriptRoot 'stage'
$stageVnc  = Join-Path $PSScriptRoot 'stage-vnc'
foreach ($d in @($stage, $stageVnc)) {
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d -Recurse -Force }
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

# --- 主体文件
Copy-Item -LiteralPath $AppExe -Destination (Join-Path $stage 'Mac远控.exe') -Force
Copy-Item -LiteralPath (Join-Path $AppDir '使用说明.txt')    -Destination $stage -Force
Copy-Item -LiteralPath (Join-Path $AppDir 'Mac 端设置.txt')  -Destination $stage -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot 'LICENSE')               -Destination $stage -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot 'THIRD-PARTY-NOTICES.txt') -Destination $stage -Force

# --- 便携 VNC 客户端（GPL-2.0，附许可证原文）
$vncSrc = Join-Path $AppDir 'bin\TigerVNC'
$vncDst = Join-Path $stageVnc 'bin\TigerVNC'
New-Item -ItemType Directory -Path $vncDst -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $vncSrc 'vncviewer.exe') -Destination $vncDst -Force
Copy-Item -LiteralPath (Join-Path $vncSrc 'LICENCE.TXT')   -Destination $vncDst -Force

# --- 编译安装包（用 /DMyAppVersion 覆盖版本号）
& $islcc "/DMyAppVersion=$Version" (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败，退出码 $LASTEXITCODE" }

$setup = Join-Path $PSScriptRoot "dist\MacRemote-Setup-$Version.exe"
if (-not (Test-Path -LiteralPath $setup)) { throw "没有生成安装包：$setup" }

# --- 便携版 zip（解压即用，免安装）
$zipRoot = Join-Path $PSScriptRoot 'dist\portable'
if (Test-Path -LiteralPath $zipRoot) { Remove-Item -LiteralPath $zipRoot -Recurse -Force }
New-Item -ItemType Directory -Path $zipRoot -Force | Out-Null
Copy-Item -Path (Join-Path $stage '*') -Destination $zipRoot -Recurse -Force
Copy-Item -Path (Join-Path $stageVnc '*') -Destination $zipRoot -Recurse -Force
$zip = Join-Path $PSScriptRoot "dist\MacRemote-Portable-$Version.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $zipRoot '*') -DestinationPath $zip -CompressionLevel Optimal

"安装包: $setup  ($([math]::Round((Get-Item $setup).Length/1MB,2)) MB)"
"便携包: $zip  ($([math]::Round((Get-Item $zip).Length/1MB,2)) MB)"
