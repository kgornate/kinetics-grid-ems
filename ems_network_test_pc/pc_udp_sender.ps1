$DEST_IP = "192.168.10.2"
$DEST_PORT = 9003
$COUNT = 5

$udp = New-Object System.Net.Sockets.UdpClient
$udp.Client.ReceiveTimeout = 2000

$remoteEndPoint = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)

for ($i = 0; $i -lt $COUNT; $i++) {
    $msg = "HELLO UDP FROM PC packet $i"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)

    Write-Host "Sending UDP message: $msg"

    $sentBytes = $udp.Send($bytes, $bytes.Length, $DEST_IP, $DEST_PORT)
    Write-Host "Sent bytes: $sentBytes"

    try {
        $rxBytes = $udp.Receive([ref]$remoteEndPoint)
        $rxMsg = [System.Text.Encoding]::UTF8.GetString($rxBytes)

        Write-Host "Received UDP response from $($remoteEndPoint.Address):$($remoteEndPoint.Port)"
        Write-Host "Response: $rxMsg"
    }
    catch {
        Write-Host "No UDP ACK received within timeout"
    }

    Start-Sleep -Seconds 1
}

$udp.Close()
Write-Host "UDP sender completed."