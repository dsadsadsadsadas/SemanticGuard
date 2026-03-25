const jwt = require('jsonwebtoken');
function verifyToken(token) {
    // VULNERABLE: Allowing 'none' algorithm by not enforcing HS256/RS256
    return jwt.verify(token, 'secret_key', { algorithms: ['none', 'HS256'] });
}
