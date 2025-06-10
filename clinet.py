# importing the required modules
import socket
import threading

HOST = '127.0.0.1'
PORT = 57815

def listen_for_messages_from_server(client):
    while True:
        try:
            message = client.recv(2048).decode('utf-8')
            if message:
                try:
                    username, content = message.split(" : ", 1)
                    print(f"\n{username}: {content}")
                except ValueError:
                    print(f"\n[Server] {message}")
            else:
                print("\n[Warning] Server sent an empty message.")
        except Exception:
            print("\n[Disconnected] Lost connection to server.")
            client.close()
            break

def send_message_to_server(client):
    while True:
        try:
            message = input("You: ")
            if message:
                client.sendall(message.encode())
            else:
                print("[Warning] Empty message not sent.")
        except Exception:
            print("[Error] Could not send message.")
            client.close()
            break

def communicate_to_server(client):
    username = input("Enter your Username: ").strip()
    if not username:
        print("[Error] Username cannot be empty.")
        exit(0)
    else:
        client.sendall(username.encode())

    threading.Thread(target=listen_for_messages_from_server, args=(client,), daemon=True).start()
    send_message_to_server(client)

def main():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((HOST, PORT))
        print(f"[Connected] to server at {HOST}:{PORT}")
    except Exception as e:
        print(f"[Error] Unable to connect to server: {e}")
        return

    communicate_to_server(client)

if __name__ == "__main__":
    main()