function generateSessionId() {
    // VULNERABLE: Predictable Session ID using weak Math.random()
    return 'sess_' + Math.random().toString(36).substr(2, 9);
}
