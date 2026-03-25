function validateEmail(email) {
    // SAFE: ReDoS safe pattern without catastrophic backtracking groups
    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (email.length > 254) return false; // Length check defense
    return emailRegex.test(email);
}
