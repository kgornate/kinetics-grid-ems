import socket

HOST = "192.168.10.2"
PORT = 9003

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"Listening for UDP on {HOST}:{PORT}")

while True:
    data, addr = sock.recvfrom(1024)
    msg = data.decode(errors="ignore")
    print(f"From {addr}: {msg}")

    reply = "ACK UDP from i.MX93: " + msg
    sock.sendto(reply.encode(), addr)
