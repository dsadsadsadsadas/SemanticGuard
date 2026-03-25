app.post('/transfer_funds', (req, res) => {
    // VULNERABLE: No CSRF token validation on state-changing POST request
    const { amount, toAccount } = req.body;
    transfer(req.session.userId, toAccount, amount);
    res.send('Success');
});
