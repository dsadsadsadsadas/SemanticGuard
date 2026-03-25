app.post('/transfer_funds', csrfProtection, (req, res) => {
    // SAFE: CSRF middleware applied
    const { amount, toAccount } = req.body;
    transfer(req.session.userId, toAccount, amount);
    res.send('Success');
});
