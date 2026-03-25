app.post('/login', async (req, res) => {
    // SAFE: Force casting to string to prevent object injection
    const username = String(req.body.username);
    const password = String(req.body.password);
    const user = await db.collection('users').findOne({ username, password });
    if (user) res.send('Logged in');
});
