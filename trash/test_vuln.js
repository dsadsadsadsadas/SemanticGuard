// TEST FILE: Vulnerable JavaScript for Taint Analysis
// This file contains intentional vulnerabilities to test detection

const express = require('express');
const { exec } = require('child_process');
const fs = require('fs');

const app = express();

// VULNERABLE: Tainted variable used in eval
app.post('/rce', (req, res) => {
    let userCode = req.body.code;
    eval(userCode);  // RCE: Tainted variable in eval
    res.send('Executed');
});

// VULNERABLE: Direct XSS
app.get('/xss', (req, res) => {
    document.getElementById('output').innerHTML = req.query.name;
});

// VULNERABLE: Command Injection
app.get('/cmd', (req, res) => {
    let command = req.query.cmd;
    exec(command);  // RCE: Command injection
});

// VULNERABLE: Path Traversal
app.get('/file', (req, res) => {
    let filename = req.params.path;
    fs.readFileSync(filename);  // Path traversal
});

// SAFE: Sanitized input (should NOT trigger)
app.get('/safe', (req, res) => {
    let count = parseInt(req.query.count);
    res.send(`Count: ${count}`);
});
