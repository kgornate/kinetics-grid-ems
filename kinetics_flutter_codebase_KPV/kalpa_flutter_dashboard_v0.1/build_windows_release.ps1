$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
Invoke-Checked "flutter" @("pub", "get")
Invoke-Checked "flutter" @("analyze", "--no-fatal-infos")
Invoke-Checked "flutter" @("test")
Invoke-Checked "dart" @("run", "tool/offline_contract_check.dart")
Invoke-Checked "flutter" @("build", "windows", "--release")
$release = Join-Path $PSScriptRoot "build\windows\x64\runner\Release"
if (-not (Test-Path $release)) { throw "Release folder not found: $release" }
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "dist") | Out-Null
$bundle = Join-Path $PSScriptRoot "dist\kalpa-gateway-windows-v0.1.zip"
Compress-Archive -Path (Join-Path $release "*") -DestinationPath $bundle -Force
Write-Host "Release bundle: $bundle"
