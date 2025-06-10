# iomporting the required modules
import socket
import threading

HOST='127.0.0.1'     # this is the like the target address where we need to connect so the target is our own computer
PORT=57815           # again the clinet can run to find a free port code or can use this particular port, its his/her choice
# note the server port and client port should be same

def listen_for_messages_from_server(client):
    while True:
        message=client.recv(2048).decode('utf-8')
        if message!="":
            username=message.split(" : ")[0]
            content=message.split(" : ")[1]
            print(f"{username}\n{content}")
        else:
            print("Server sent an empty message")
            exit(0)

# now the function for client to send the message
def send_message_to_server(client):
    while True:
        message=input("Message: ")
        if message!="":
            client.sendall(message.encode())
        else:
            print("Empty Message")

def communicate_to_server(client):
    username=input("Enter your Username: ")
    if username=="":
        print("Username cannot be empty")
        exit(0)
    else:
        client.sendall(username.encode())

    # now we want communication and listen to server at the same time so we will use threading
    threading.Thread(target=listen_for_messages_from_server,args=(client,)).start()
    send_message_to_server(client)


def main():
    '''
        we created a socket class object where AF_INET says we will use the IPv4 addresss and sock stream says
        we will use tcp packets for communication
    
    '''
    client=socket.socket(socket.AF_INET,socket.SOCK_STREAM)

    # now connect to the server
    try:
        client.connect((HOST,PORT))
        print(f"Sucessfully connected to the server host: {HOST} and port: {PORT}")
    except:
        print(f"Unable to connect to server host: {HOST} and port: {PORT}")
    
    communicate_to_server(client)     #no need of threading cuz there is only one clinet per computer

if __name__=="__main__":
    main()