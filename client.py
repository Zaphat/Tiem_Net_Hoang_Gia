import socket
import threading

# create a socket object
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# get local machine name
host = socket.gethostname()
port = 9999

# connect to the server
client.connect((host, port))

# receive messages from server
def receive():
    while True:
        try:
            # receive message from server
            # if 'NICK' send nickname
            message = client.recv(1024).decode('ascii')
            if message == 'NICK':
                client.send(nickname.encode('ascii'))
            else:
                print(message)
        except:
            # close connection when error
            print('An error occured!')
            client.close()
            break

# send messages to server
def write():
    while True:
        message = f'{nickname}: {input("")}'
        client.send(message.encode('ascii'))


# request and store nickname
nickname = input('Choose your nickname: ')

# start threads for listening and writing
receive_thread = threading.Thread(target=receive)
receive_thread.start()
write_thread = threading.Thread(target=write)
write_thread.start()