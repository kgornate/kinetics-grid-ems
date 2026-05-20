$client = New-Object System.Net.Sockets.TcpClient
$client.Connect("192.168.10.2", 9000)

$stream = $client.GetStream()
$writer = New-Object System.IO.StreamWriter($stream)
$reader = New-Object System.IO.StreamReader($stream)

$writer.AutoFlush = $true

$msg = "HELLO FROM PC"
Write-Host "Sending TCP message: $msg"

$writer.WriteLine($msg)

$response = $reader.ReadLine()
Write-Host "Received response: $response"

$client.Close()