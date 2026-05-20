$PORT = 9013
$MAX_PACKETS = 5

Write-Host "Starting UDP listener on port $PORT..."

try {

    $udp = New-Object System.Net.Sockets.UdpClient($PORT)

    $remote = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)

    Write-Host "Listening for UDP telemetry..."
    Write-Host "Will automatically stop after $MAX_PACKETS packets."

    for ($i = 0; $i -lt $MAX_PACKETS; $i++) {

        $data = $udp.Receive([ref]$remote)

        $msg = [System.Text.Encoding]::UTF8.GetString($data)

        Write-Host "From $($remote.Address):$($remote.Port) -> $msg"
    }

}
catch {

    Write-Host "UDP listener error:"
    Write-Host $_.Exception.Message

}
finally {

    if ($udp) {
        $udp.Close()
    }

    Write-Host ""
    Write-Host "UDP listener stopped."
}