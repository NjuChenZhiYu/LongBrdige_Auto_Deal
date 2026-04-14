import socket
import sys

def check_port(host, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f"Port {port} is OPEN")
            return True
        else:
            print(f"Port {port} is CLOSED (Code: {result})")
            return False
    except Exception as e:
        print(f"Error checking port {port}: {e}")
        return False

if __name__ == "__main__":
    host = "127.0.0.1"
    ports = [11111, 45575, 111111]
    
    print(f"Checking ports on {host}...")
    for p in ports:
        check_port(host, p)
