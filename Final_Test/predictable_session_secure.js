const crypto = require('crypto');
function generateSessionId() {
    // SAFE: Cryptographically secure Session ID generation
    return 'sess_' + crypto.randomBytes(32).toString('hex');
}
