import threading
balance = 100
def withdraw(amount):
    global balance
    # VULNERABLE: Race Condition (TOCTOU) during balance check and update
    if balance >= amount:
        # simulate delay
        import time; time.sleep(0.1)
        balance -= amount
        return True
    return False
