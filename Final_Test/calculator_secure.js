// Secure Calculator Service
const math = require('mathjs');

function calculateExpression(userInput) {
    // SECURE: Using math.js parser instead of eval
    try {
        const result = math.evaluate(userInput);
        return result;
    } catch (error) {
        throw new Error('Invalid mathematical expression');
    }
}

function safeCalculate(a, b, operation) {
    // SECURE: Whitelist allowed operations
    const operations = {
        'add': (x, y) => x + y,
        'subtract': (x, y) => x - y,
        'multiply': (x, y) => x * y,
        'divide': (x, y) => x / y
    };
    
    if (!operations[operation]) {
        throw new Error('Invalid operation');
    }
    
    return operations[operation](a, b);
}

module.exports = { calculateExpression, safeCalculate };
