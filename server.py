''' 
Implements a simple chat server where multiple clients can connect, send messages, and receive messages from 
others in real time using TCP sockets 
'''

# import required modules
import socket       # for making a low level networking interface
import threading    # handles multiple client operations at one time

# now i will provide the server host and port for the communication
HOST = '127.0.0.1'    # Localhost
PORT = 57815          # Port for communication
LISTENER_LIMIT = 5
active_clients = []   # List contains all active clients (username, client_socket)

# function to handel client
'''
here we are using the client object we get from the server.accept()
'''

# creating a function to send message to client
def send_message_to_client(client, message):
    try:
        client.sendall(message.encode())
    except Exception as e:
        print(f"[!] Error sending message to client: {e}")

# function to send any new message to all the client that are connected to the server
def send_messages_to_all(sender_client, message):
    for user in active_clients:
        if user[1] != sender_client:  # Don't send the message back to the sender
            send_message_to_client(user[1], message)

# function to listen for any upcomming messages from the client
def listen_for_messages(username, client):
    while True:
        try:
            # here we will recieve the message from the user
            response = client.recv(2048).decode('utf-8')

            # and checking if the message is empty or not
            if response:
                final_msg = f"{username} : {response}"
                print(f"\033[92m[Message]\033[0m {final_msg}")
                send_messages_to_all(client, final_msg)    #calling the send message to all function 
            else:
                print(f"\033[93m[Warning]\033[0m Empty message from {username}.")
        except Exception as e:
            print(f"\033[91m[Disconnected]\033[0m {username} has left the chat.")
            active_clients[:] = [user for user in active_clients if user[1] != client]
            client.close()
            break

def client_handler(client):
    # user shuld send the username of client to the sever so we will handel that now
    while True:
        try:
            # this is the part where we will recive the username and .decode is the unicode type and 2048 is the message size
            # since all the messages are sent in the form of bytes so we need to decode it in the server side.
            username = client.recv(2048).decode('utf-8')
            if username:
                active_clients.append((username, client))
                print(f"\033[94m[Connected]\033[0m {username} joined the chat.")
                break                                       #adding their username and also object which will be useful for carrying out future operations
            else:
                print("\033[93m[Warning]\033[0m Client username cannot be empty!")
        except Exception as e:
            print(f"\033[91m[Error]\033[0m Error receiving username: {e}")
            client.close()
            return
    threading.Thread(target=listen_for_messages, args=(username, client), daemon=True).start()

# main fucntion
def main():
    '''
        we created a socket class object where AF_INET says we will use the IPv4 addresss and sock stream says
        we will use tcp packets for communication
    
    '''
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("\033[96m[Server]\033[0m Starting server...")

    # now creating a try and catch block

    try:
        '''
        now we need to provide the address to the server in the form of hostip and which port it is going to use
        '''
        server.bind((HOST, PORT))
        print(f"\033[96m[Server]\033[0m Running at {HOST}:{PORT}")
    except Exception as e:
        print(f"\033[91m[Error]\033[0m Unable to bind to {HOST}:{PORT} - {e}")
        return

    '''
    now we will set the server limit this is necessary so that more load doesn't come to our 
    computer so we will set the limit how many clinet can connect to our server at a time 
    '''
    server.listen(LISTENER_LIMIT)
    print(f"\033[96m[Server]\033[0m Listening for connections (limit: {LISTENER_LIMIT})...")

    ''' now we will create a while loop that will continously listen to clinet connections'''

    while True:
        try:
            client, address = server.accept()  # we created two varaibles that contain the clinet socket using and what is the address of it
            print(f"\033[92m[New Connection]\033[0m {address[0]}:{address[1]}")
            threading.Thread(target=client_handler, args=(client,), daemon=True).start()
        except KeyboardInterrupt:
            print("\n\033[91m[Server]\033[0m Shutting down.")
            break
        except Exception as e:
            print(f"\033[91m[Error]\033[0m {e}")

if __name__ == "__main__":
    main()