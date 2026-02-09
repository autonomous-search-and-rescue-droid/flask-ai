import socket

# Listen on all interfaces so we can receive from outside
UDP_IP = "0.0.0.0" 
# This port must match what you send in the URL (e.g. &port=9999)
UDP_PORT = 9999

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock.bind((UDP_IP, UDP_PORT))
    print(f"Listening for movement commands on port {UDP_PORT}...")
    print("Press Ctrl+C to stop.")

    while True:
        data, addr = sock.recvfrom(1024) # buffer size is 1024 bytes
        print(f"Received from {addr}: {data.decode()}")
except OSError as e:
    print(f"Error: Could not bind to port {UDP_PORT}. Is it already in use?")
    print(f"Details: {e}")
except KeyboardInterrupt:
    print("\nStopping listener...")
finally:
    sock.close()
