app.get('/search', (req, res) => {
    // VULNERABLE: HPP - Express parses array if multiple `q` params exist, crashing the DB query
    const query = req.query.q;
    db.search({ where: { title: { [Op.like]: '%' + query + '%' } } });
    res.send('OK');
});
