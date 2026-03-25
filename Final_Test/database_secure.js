// Secure Database Module
const mysql = require('mysql');

function getUserByEmail(email) {
    const connection = mysql.createConnection({
        host: process.env.DB_HOST,
        user: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME
    });
    
    // SECURE: Parameterized query prevents SQL injection
    const query = 'SELECT * FROM users WHERE email = ?';
    connection.query(query, [email], (err, results) => {
        if (err) throw err;
        console.log(results);
    });
}

async function searchUsers(searchTerm) {
    const connection = mysql.createConnection({
        host: process.env.DB_HOST,
        user: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
        database: process.env.DB_NAME
    });
    
    // SECURE: Parameterized query
    const query = 'SELECT * FROM users WHERE username LIKE ?';
    return new Promise((resolve, reject) => {
        connection.query(query, [`%${searchTerm}%`], (err, results) => {
            if (err) reject(err);
            else resolve(results);
        });
    });
}

module.exports = { getUserByEmail, searchUsers };
