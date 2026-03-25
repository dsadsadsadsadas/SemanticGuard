app.post('/updateUser', async (req, res) => {
    // SAFE: Explicit field picking prevents mass assignment
    const user = await User.findById(req.user.id);
    const { email, name, bio } = req.body;
    Object.assign(user, { email, name, bio });
    await user.save();
    res.send(user);
});
