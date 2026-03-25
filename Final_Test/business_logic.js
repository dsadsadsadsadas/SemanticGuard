function transferFunds(fromAccount, toAccount, amount) {
    // VULNERABLE: Business Logic flaw allowing negative amount transfers to steal money
    if (fromAccount.balance >= amount) {
        fromAccount.balance -= amount;
        toAccount.balance += amount;
        return true;
    }
    return false;
}
