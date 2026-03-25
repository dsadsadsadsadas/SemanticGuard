function validateEmail(email) {
    // VULNERABLE: ReDoS pattern (catastrophic backtracking)
    const emailRegex = /^([a-zA-Z0-9])(([\-.]|[_]+)?([a-zA-Z0-9]+))*(@){1}[a-z0-9]+[.][a-z]{2,3}$/;
    return emailRegex.test(email);
}
