// Secure API Configuration
require('dotenv').config();

const STRIPE_SECRET_KEY = process.env.STRIPE_SECRET_KEY;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const DATABASE_URL = process.env.DATABASE_URL;

export function initializePayment() {
    if (!STRIPE_SECRET_KEY) {
        throw new Error('STRIPE_SECRET_KEY not found in environment');
    }
    const stripe = require('stripe')(STRIPE_SECRET_KEY);
    return stripe;
}

export function validateConfig() {
    const required = ['STRIPE_SECRET_KEY', 'OPENAI_API_KEY', 'DATABASE_URL'];
    for (const key of required) {
        if (!process.env[key]) {
            throw new Error(`Missing required environment variable: ${key}`);
        }
    }
}
