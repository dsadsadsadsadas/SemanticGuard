// Database Module
const mysql = require('mysql');

function getUserByEmail(email) {
    const connection = mysql.createConnection({
        host: 'localhost',
        user: 'root',
        password: 'root',
        database: 'myapp'
    });
    
    // VULNERABLE: SQL Injection
    const query = `SELECT * FROM users WHERE email = '${email}'`;
    connection.query(query, (err, results) => {
        console.log(results);
    });
}

module.exports = { getUserByEmail };
