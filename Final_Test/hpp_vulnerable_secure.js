const hpp = require('hpp');
app.use(hpp()); // SAFE: Express middleware prevents HTTP Parameter Pollution array payloads
app.get('/search', (req, res) => {
    const query = req.query.q;
    db.search({ where: { title: { [Op.like]: '%' + query + '%' } } });
    res.send('OK');
});
