''' 
Implements a simple chat server where multiple clients can connect, send messages, and receive messages from 
others in real time using TCP sockets 
'''

# import required modules
import socket       # for making a low level netwroking interface
import threading    # handels ,multiple clinet operations at one time

# now i will provide the server host and port for the communication
HOST='127.0.0.1'    # this means our own local machine is used as a server for the communication
PORT=57815  # we can use any port for our use cases
LISTENER_LIMIT=5
active_clients=[]   # list contains all active clients

# function to handel client
'''
here we are using the client object we get from the server.accept()
'''

# creating a function to send message to client
def send_message_to_client(client,message):
    client.sendall(message.encode())
    print(message)    #using the client object there is a method to send all the message and we have to encode also the message

# function to send any new message to all the client that are connected to the server
def send_messages_to_all(client,message):
    for user in active_clients:
        send_message_to_client(user[1],message)         # here we passed the user[1] because it contains the client object in active client list

# function to listen for any upcomming messages from the client
def listen_for_messages(username,client):
    while True:
        # here we will recieve the message from the user
        response=client.recv(2048).decode('utf-8')

        # and checking if the message is empty or not
        if response!="":
            final_msg=username+" : "+response 
            print(final_msg)      # here i am formatting the how message will look like
            send_messages_to_all(client,final_msg)    #calling the send message to all function 
        else:
            print(f"Message from {username} is empty !")


def client_handler(client):
    # user shuld send the username of client to the sever so we will handel that now
    while True:
        # this is the part where we will recive the username and .decode is the unicode type and 2048 is the message size
        # since all the messages are sent in the form of bytes so we need to decode it in the server side.
        username=client.recv(2048).decode('utf-8')
        if username!="":
            active_clients.append((username,client))
            break                                       #adding their username and also object which will be useful for carrying out future operations
        else:
            print("Client username cannot be empty !")

    
    threading.Thread(target=listen_for_messages,args=(username,client,)).start()
        
# main fucntion
def main():
    '''
        we created a socket class object where AF_INET says we will use the IPv4 addresss and sock stream says
        we will use tcp packets for communication
    
    '''
    server=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    print("Server is running...")

    # now creating a try and catch block

    try:
        '''
        now we need to provide the address to the server in the form of hostip and which port it is going to use
        '''
        server.bind((HOST,PORT))
        print(f"server is running at host: {HOST} and port: {PORT}")
    except:
        print(f"Unable to bind with the host {HOST} and port {PORT}")

    '''
    now we will set the server limit this is necessary so that more load doesn't come to our 
    computer so we will set the limit how many clinet can connect to our server at a time 
    '''
    server.listen(LISTENER_LIMIT)

    ''' now we will create a while loop that will continously listen to clinet connections'''

    while True:
        client,address=server.accept()  # we created two varaibles that contain the clinet socket using and what is the address of it
        print(f"Sucessfully connected to client {address[0]} {address[1]}") 
        # here address is the tuple so address[0] will print the host and address[1] will print the port which is using

        '''
        This approach allows the server to handle multiple clients at the same time. Each client gets its own 
        thread, so one slow or busy client won't block others
        '''
        threading.Thread(target=client_handler,args=(client,)).start()


if __name__=="__main__":
    main()