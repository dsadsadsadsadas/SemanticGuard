app.post('/login', async (req, res) => {
    // VULNERABLE: NoSQL injection via object payloads (e.g. {"username": {"$ne": null}})
    const { username, password } = req.body;
    const user = await db.collection('users').findOne({ username, password });
    if (user) res.send('Logged in');
});
