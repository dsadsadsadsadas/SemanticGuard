const express = require('express');
const app = express();

app.get('/user', (req, res) => {
    const userId = req.params.id;
    const email = req.query.email;
    const safeName = sanitize_input(userId);
    console.log(email);
    res.json({ id: safeName });
});
