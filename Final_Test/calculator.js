// Calculator Service
function calculateExpression(userInput) {
    // VULNERABLE: eval with user input
    const result = eval(userInput);
    return result;
}

function executeCode(code) {
    // VULNERABLE: Function constructor
    const fn = new Function(code);
    return fn();
}

module.exports = { calculateExpression, executeCode };
