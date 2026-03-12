# =============================================================
#   Chat-Connect — TCP Chat Application
#   Original Creator : Prajjwal
#   © 2025  All Rights Reserved.
#   Unauthorized copying or redistribution is strictly prohibited.
# =============================================================
'''
programm to find a free port on your computer using the coket module. run this
code once to let os itself assign you a free port ;)

'''
import socket
s = socket.socket()
s.bind(('', 0))
print(s.getsockname()[1])
s.close()
