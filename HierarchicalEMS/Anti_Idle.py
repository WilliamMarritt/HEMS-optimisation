import ctypes
import time

print("Anti-idle script running.")

MOUSEEVENTF_MOVE = 0x0001

while True:
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0)
    time.sleep(1)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, 0)
    time.sleep(59)
    