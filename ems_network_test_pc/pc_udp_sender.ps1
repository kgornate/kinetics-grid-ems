$DEST_IP = "192.168.10.2"
$DEST_PORT = 9003
$COUNT = 5

$udp = New-Object System.Net.Sockets.UdpClient

for ($i = 0; $i -lt $COUNT; $i++) {
    $msg = "HELLO UDP FROM PC packet $i"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)

    Write-Host "Sending UDP message: $msg"

    $udp.Send($bytes, $bytes.Length, $DEST_IP, $DEST_PORT)

    Start-Sleep -Seconds 1
}

$udp.Close()
Write-Host "UDP sender completed."