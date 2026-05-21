import socket

HOST = "192.168.10.2"
PORT = 9003

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"Listening for UDP on {HOST}:{PORT}")
print("Press Ctrl+C to stop")

packet_count = 0

try:
    while True:
        data, addr = sock.recvfrom(1024)
        packet_count += 1

        msg = data.decode(errors="ignore")
        print(f"[{packet_count}] From {addr}: {msg}")

        reply = "ACK UDP from i.MX93: " + msg
        sock.sendto(reply.encode(), addr)

except KeyboardInterrupt:
    print("Stopped by user")

finally:
    sock.close()
    print("UDP listener closed")