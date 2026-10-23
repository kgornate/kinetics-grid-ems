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
Invoke-Checked "dart" @("run", "tool/kalpa_category_contract_check.dart")
Invoke-Checked "flutter" @("run", "-d", "windows")
