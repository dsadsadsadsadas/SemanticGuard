import threading
balance = 100
lock = threading.Lock()
def withdraw(amount):
    global balance
    # SAFE: Mutex lock prevents race condition
    with lock:
        if balance >= amount:
            import time; time.sleep(0.1)
            balance -= amount
            return True
        return False
