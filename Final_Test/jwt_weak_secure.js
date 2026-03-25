const jwt = require('jsonwebtoken');
function verifyToken(token) {
    // SAFE: Enforcing strict cryptographic algorithms
    return jwt.verify(token, 'secret_key', { algorithms: ['HS256'] });
}
