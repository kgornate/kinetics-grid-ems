import socket
import time

PC_IP = "192.168.10.1"
PC_PORT = 9013

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

for i in range(5):
    msg = f"UDP telemetry packet {i} from i.MX93"
    sock.sendto(msg.encode(), (PC_IP, PC_PORT))
    print("Sent:", msg)
    time.sleep(1)

sock.close()
