# Chat-Application

A simple real-time chat application built with Python using the `socket` module for backend communication and (optionally) `Flask` for the web interface.

## Features

- Real-time messaging between multiple users
- Command-line client for chat
- Easy to set up and run locally
- Uses Python's standard `socket` module for networking

## Communication Sequence

To help you understand how the chat server works, here’s a visual overview of the communication sequence:

![Chat Server Communication Sequence](./chat_server_communication_sequence.png)

---

## How This Project Works

### Server Side

- The server is started using `python server.py`.
- It listens for incoming client connections on `127.0.0.1` and the specified port.
- For each client, it receives a username, validates it, and starts a new thread to handle messages from that client.
- When a client sends a message, the server broadcasts it to all connected clients and prints it on the server terminal.

### Client Side

- The client is started using `python clinet.py`.
- The user is prompted to enter a username.
- The client connects to the server and sends the username.
- The client can send messages to the server, which are then broadcast to all other clients.
- The client also listens for messages from the server and displays them in real time.

#### Client-Server Communication Sequence

Below is a visual representation of how the client communicates with the server:

![Client-Server Communication Sequence](./client_server_communication_sequence.png)

---

## Example: Terminal Working

Below is an example screenshot showing the server and client running in separate terminals:

![Terminal Working Example](./terminal_working_example.png)

*Left: Server terminal showing received messages. Right: Client terminal for sending and receiving messages.*

---

## Requirements

- Python 3.x

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/Chat-Application.git
    cd Chat-Application
    ```

2. (Optional) Install Flask if you plan to use a web interface later:
    ```sh
    pip install Flask
    ```

## Usage

### 1. Find a Free Port (Optional)

If you want to use a different port, you can run the provided script to find a free port:
```sh
python to_find_a_free_port.py
```
Update the `PORT` variable in both `server.py` and `clinet.py` if you change the port.

### 2. Start the Chat Server

```sh
python server.py
```

### 3. Start the Client(s)

Open a new terminal for each client and run:
```sh
python clinet.py
```
Make sure the `HOST` and `PORT` in `clinet.py` match those in `server.py`.

### 4. Chat!

Each client will connect to the server and can send/receive messages in real time.

---

## Project Structure

```
Chat-Application/
├── server.py                              # Chat server using sockets
├── clinet.py                              # Command-line chat client
├── to_find_a_free_port.py                 # Utility to find a free port
├── static/                                # (For future Flask web interface)
├── templates/                             # (For future Flask web interface)
├── chat_server_communication_sequence.png # Server communication diagram
├── client_server_communication_sequence.png # Client communication diagram
├── terminal_working_example.png           # Screenshot of terminal working
└── README.md
```

## Notes

- The server listens on `127.0.0.1` (localhost), so only clients on the same machine can connect.
- You can extend this project by adding a Flask web interface in the future.

## License

This project is licensed under the MIT License.