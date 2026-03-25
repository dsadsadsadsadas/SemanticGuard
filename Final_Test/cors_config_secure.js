const express = require('express');
const cors = require('cors');
const app = express();
// SAFE: Strict CORS origin
app.use(cors({
    origin: 'https://trusted.example.com',
    credentials: true
}));
