app.post('/updateUser', async (req, res) => {
    // VULNERABLE: Mass Assignment - directly saving req.body allows overriding `isAdmin`
    const user = await User.findById(req.user.id);
    Object.assign(user, req.body);
    await user.save();
    res.send(user);
});
