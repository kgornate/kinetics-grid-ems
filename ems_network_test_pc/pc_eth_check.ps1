Write-Host "======================================"
Write-Host "PC Ethernet Check"
Write-Host "======================================"

Write-Host "`n[1] IP Configuration:"
ipconfig

Write-Host "`n[2] Network Profile:"
Get-NetConnectionProfile

Write-Host "`n[3] Ping i.MX93:"
ping 192.168.10.2

Write-Host "======================================"
Write-Host "PC Ethernet check completed"
Write-Host "======================================"