import socket
import threading
import ctypes
from sortedcontainers import SortedDict
import re
import sys
import os
import uuid
# CLIENT[NICKNAME] = [SOCKET, ADDRESS]
# {bytes: [socket.socket, (str, int)]}
CLIENTS = SortedDict()

# FILES[TOKEN] = (filename,file_server_path,owner)
# {str: (bytes,str,bytes)}
FILES = dict()
LOCATION = uuid.uuid4().hex

# create sockets for different purposes
chat_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
file_upload_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
file_download_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# get local machine name
CHAT_HOST = socket.gethostname()
FILE_UPLOAD_HOST = CHAT_HOST
FILE_DOWNLOAD_HOST = CHAT_HOST
CHAT_PORT = 9999
FILE_UPLOAD_PORT = 8080
FILE_DOWNLOAD_PORT = 9000


# allow only one instance of the chat_server to run
try:
    chat_server.bind((CHAT_HOST, CHAT_PORT))
    file_upload_server.bind((FILE_UPLOAD_HOST, FILE_UPLOAD_PORT))
    file_download_server.bind((FILE_DOWNLOAD_HOST, FILE_DOWNLOAD_PORT))
except:
    ctypes.windll.user32.MessageBoxW(
        0, "Another instance of the server is already running!", "Error", 1)
    sys.exit(0)
# listen for clients
chat_server.listen()
file_upload_server.listen()
file_download_server.listen()


def private_message(client_socket, nickname, message) -> None:
    structure = re.compile(r'^(/private)\s\((.{2,16})\)\s(.+)$')
    _, receiver, text = structure.match(message.decode('utf-8')).groups()
    lookup_nickname = receiver.encode('utf-8')
    if lookup_nickname not in CLIENTS:
        send_to_client(
            client_socket, '————> User not found. Please try again.')
        return
    send_to_client(CLIENTS[lookup_nickname][0],
                   f'[Private from {nickname.decode("utf-8")}]: {text}')


def send_to_client(client_socket, message) -> None:
    # padding to make each message 1024 bytes
    # if message is larger than 1024 bytes, then store the rest in a list
    # and send the list to the client
    # message in string format
    # format each message to be 1024 bytes
    # reference: https://stackoverflow.com/questions/39479036/python-make-sure-to-send-1024-bytes-at-a-time
    if len(message) < 1024:
        message = message + (1024-len(message))*'\x00'
        client_socket.send(message.encode('utf-8'))
    else:
        message_list = []
        while len(message) > 1024:
            message_list.append(message[:1024])
            message = message[1024:]
        if len(message):
            message_list.append(message + (1024-len(message))*'\x00')
        for message in message_list:
            client_socket.send(message.encode('utf-8'))


# broadcast messages to all clients


def broadcast(message, nickname, sender=None) -> None:
    # notification message
    if sender is None or nickname == "SERVER":
        notification = (85-len(message))//2 * ' '  \
            + '-'*6 + "   " + message + "   " + '-' * \
            6 + (85-len(message))//2 * ' '+'\n'
        for client_socket, address in CLIENTS.values():
            send_to_client(client_socket, notification)
    else:
        for client_socket, address in CLIENTS.values():
            if client_socket is not sender:
                send_to_client(client_socket,
                               f'[{nickname.decode("utf-8")}]: {message.decode("utf-8")}')

# handle client messages


def handle(client_socket, nickname) -> None:
    while True:
        try:
            # receive message from client
            message = client_socket.recv(1024)
            if message.startswith((b'/private')):
                private_message(client_socket, nickname, message)
                continue
            # public message- broadcast to all clients
            broadcast(message, nickname, client_socket)
        except:
            # remove client from CLIENTS
            del CLIENTS[nickname]
            # notify to all clients
            broadcast(
                f'{nickname.decode("utf-8")} left the chatroom!', "SERVER")
            # notify all clients to update their client list
            for client_socket, _ in CLIENTS.values():
                send_to_client(client_socket, '\x00REMOVE ' +
                               f"({nickname.decode('utf-8')})")
            break


# update client list

def update_client_list(new_client, storing_nickname) -> None:
    display_nickname = storing_nickname.decode('utf-8')
    for client_socket, _ in CLIENTS.values():
        send_to_client(client_socket, '\x00UPDATE ' +
                       f"({display_nickname})")
    for user in CLIENTS:
        if user != storing_nickname:
            send_to_client(new_client, '\x00UPDATE ' +
                           f"({user.decode('utf-8')})")


# on connect new client

def on_connect(client_socket, address) -> None:
    # request and store nickname
    try:
        storing_nickname = client_socket.recv(1024)  # bytes
        display_nickname = storing_nickname.decode('utf-8')  # string

        # check if nickname is already taken
        while storing_nickname in CLIENTS:
            client_socket.send(
                'RESEND_NICK'.encode('utf-8'))
            storing_nickname = client_socket.recv(1024)
            display_nickname = storing_nickname.decode('utf-8')

        # store client information
        CLIENTS[storing_nickname] = (client_socket, address)

        # notify to all clients
        broadcast(f'{display_nickname} joined the chatroom!', "SERVER")

        # notify all clients to update their client list
        update_thread = threading.Thread(
            target=update_client_list, args=(client_socket, storing_nickname))
        update_thread.start()
        # start thread for handling client
        thread = threading.Thread(
            target=handle, args=(client_socket, storing_nickname))
        thread.start()
    except:
        return

# start accepting clients


def accept_chat() -> None:
    while True:
        try:
            client_socket, address = chat_server.accept()
            print(f'Connected with {str(address)}')
            thread = threading.Thread(
                target=on_connect, args=(client_socket, address))
            thread.start()
        except:
            break

# listen for file upload


def on_file_upload(client_socket) -> None:
    try:
        metadata = client_socket.recv(2048)
        # /upload (filename) (sender)
        structure = re.compile(r'^(/upload)\s\((.{2,16})\)\s\((.+)\).*$')
        _, sender, filename = structure.match(
            metadata.decode('utf-8')).groups()

        client_socket.send('READY'.encode('utf-8'))
        # open directory for file storing
        if not os.path.exists(LOCATION):
            os.makedirs(LOCATION)
        # generate a unique token for the file
        TOKEN = uuid.uuid4().hex
        while TOKEN in FILES:
            TOKEN = uuid.uuid4().hex
        # store file information
        FILES[TOKEN] = (
            filename.encode('utf-8'), f'{LOCATION}/{TOKEN}.{filename.split(".")[-1]}', sender.encode('utf-8'))
        # store file in the directory
        with open(f'{FILES[TOKEN][1]}', 'wb') as file:
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                file.write(data)
        # notify the sender that the file has been uploaded
        broadcast(
            f'{sender} has uploaded a file', "SERVER")
        # update the file list for all clients
        for client_socket, _ in CLIENTS.values():
            send_to_client(client_socket, '\x00UPDATE_FILE ' +
                           f"({filename}) ({TOKEN})")
    except:
        return


def accept_file_upload() -> None:
    while True:
        try:
            client_socket, address = file_upload_server.accept()
            thread = threading.Thread(
                target=on_file_upload, args=(client_socket,))
            thread.start()
        except:
            break


# listen for file download
def on_file_download(client_socket) -> None:
    try:
        TOKEN = client_socket.recv(1024).decode('utf-8')
        if TOKEN not in FILES:
            return
        client_socket.send(FILES[TOKEN][0])

        # send file content to client
        with open(f'{FILES[TOKEN][1]}', 'rb') as file:
            while True:
                data = file.read(1024)
                if not data:
                    break
                client_socket.send(data)
        client_socket.close()
    except:
        return


def accept_file_download() -> None:
    while True:
        try:
            client_socket, address = file_download_server.accept()
            thread = threading.Thread(
                target=on_file_download, args=(client_socket,))
            thread.start()
        except:
            break


if __name__ == '__main__':
    import tkinter as tk
    import sys
    import shutil
    root = tk.Tk()

    def on_closing():
        root.destroy()
        chat_server.close()
        file_upload_server.close()
        file_download_server.close()
        for client_socket, _ in CLIENTS.values():
            client_socket.close()
        if os.path.exists(LOCATION):
            shutil.rmtree(LOCATION)
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Set the window's position
    root.geometry(
        f"{300}x{100}+{(root.winfo_screenwidth() - 300) // 2}+{(root.winfo_screenheight() - 100) // 2}")
    # set the title
    root.title("SERVER IS ONLINE!")
    root.resizable(False, False)
    # display CHAT_HOST and CHAT_PORT on tkinter windows (centered)
    tk.Label(root, text=f"HOST: {CHAT_HOST}").pack(pady=10)
    tk.Label(root, text=f"PORT: {CHAT_PORT}").pack(pady=10)

    # start accepting clients
    accept_chat_thread = threading.Thread(target=accept_chat)
    accept_chat_thread.start()

    # start accepting file upload
    accept_file_upload_thread = threading.Thread(target=accept_file_upload)
    accept_file_upload_thread.start()

    # start accepting file download
    accept_file_download_thread = threading.Thread(target=accept_file_download)
    accept_file_download_thread.start()

    root.mainloop()
