const express = require('express');
const app = express();

app.get('/patient/:id', (req, res, next) => {
    try {
        const internal_data = db.getPatient(req.params.id);
        console.log("Debug info:", internal_data);
        res.status(200).json({ success: true, user: safeFormat(internal_data) });
    } catch (err) {
        res.status(500).json({ message: err.message, stack: err.stack });
    }
});
