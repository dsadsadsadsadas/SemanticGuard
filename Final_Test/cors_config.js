const express = require('express');
const cors = require('cors');
const app = express();
// VULNERABLE: Insecure CORS allowing any origin with credentials
app.use(cors({
    origin: '*',
    credentials: true
}));
