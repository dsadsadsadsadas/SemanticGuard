function transferFunds(fromAccount, toAccount, amount) {
    // SAFE: Business Logic defense enforcing positive amounts
    if (amount <= 0) throw new Error("Invalid transfer amount");
    if (fromAccount.balance >= amount) {
        fromAccount.balance -= amount;
        toAccount.balance += amount;
        return true;
    }
    return false;
}
