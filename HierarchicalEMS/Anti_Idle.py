import ctypes
import time

print("Anti-idle script running.")

MOUSEEVENTF_MOVE = 0x0001
ALT = 0x12
TAB = 0x09


while True:
    ctypes.windll.user32.keybd_event(ALT, 0,0,0)
    ctypes.windll.user32.keybd_event(TAB, 0,0,0)
    
    ctypes.windll.user32.keybd_event(ALT, 0,2,0)
    ctypes.windll.user32.keybd_event(TAB, 0,2,0)

    time.sleep(30)
    
    