import socket

HOST = "192.168.10.2"
PORT = 9003
MAX_PACKETS = 5

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"Listening for UDP on {HOST}:{PORT}")
print(f"Will stop after {MAX_PACKETS} packets")

try:
    for i in range(MAX_PACKETS):
        data, addr = sock.recvfrom(1024)
        msg = data.decode(errors="ignore")
        print(f"[{i+1}/{MAX_PACKETS}] From {addr}: {msg}")

        reply = "ACK UDP from i.MX93: " + msg
        sock.sendto(reply.encode(), addr)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    sock.close()
    print("UDP listener closed")
