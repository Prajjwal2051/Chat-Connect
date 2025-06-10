# iomporting the required modules
import socket
import threading

HOST = '127.0.0.1'
PORT = 57815

def listen_for_messages_from_server(client):
    while True:
        try:
            message = client.recv(2048).decode('utf-8')
            if message:
                username, content = message.split(" : ", 1)
                print(f"\033[94m{username}\033[0m: {content}")
            else:
                print("\033[93m[Warning]\033[0m Server sent an empty message.")
        except Exception as e:
            print("\033[91m[Disconnected]\033[0m Lost connection to server.")
            client.close()
            break

def send_message_to_server(client):
    while True:
        try:
            message = input("\033[92mYou:\033[0m ")
            if message:
                client.sendall(message.encode())
            else:
                print("\033[93m[Warning]\033[0m Empty message not sent.")
        except Exception as e:
            print("\033[91m[Error]\033[0m Could not send message.")
            client.close()
            break

def communicate_to_server(client):
    username = input("Enter your Username: ").strip()
    if not username:
        print("\033[91m[Error]\033[0m Username cannot be empty.")
        exit(0)
    else:
        client.sendall(username.encode())

    threading.Thread(target=listen_for_messages_from_server, args=(client,), daemon=True).start()
    send_message_to_server(client)

def main():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((HOST, PORT))
        print(f"\033[96m[Connected]\033[0m to server at {HOST}:{PORT}")
    except Exception as e:
        print(f"\033[91m[Error]\033[0m Unable to connect to server: {e}")
        return

    communicate_to_server(client)

if __name__ == "__main__":
    main()