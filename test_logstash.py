import socket
import json
import time


def test_logstash_connection():
    """Test TCP connection to Logstash"""
    host = "localhost"
    port = 5141

    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        print(f"Successfully connected to {host}:{port}")

        # Test message
        test_message = {
            "@timestamp": "2024-11-24T22:30:00.000Z",
            "message": "Test message from Python",
            "level": "INFO",
            "app_name": "test-script",
            "type": "syslog-modern"
        }

        # Send message
        message = json.dumps(test_message) + "\n"
        sock.send(message.encode())
        print(f"Sent message: {message}")

        # Keep connection open briefly
        time.sleep(1)

        # Close connection
        sock.close()
        print("Connection closed")

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    test_logstash_connection()