import socket

HOST = "192.168.10.2"
PORT = 9000

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(1)

print(f"TCP server listening on {HOST}:{PORT}")

conn, addr = server.accept()
print("Connected by:", addr)

while True:
    data = conn.recv(1024)
    if not data:
        break

    msg = data.decode(errors="ignore").strip()
    print("Received:", msg)

    response = "ACK from i.MX93: " + msg + "\n"
    conn.sendall(response.encode())

conn.close()
server.close()
