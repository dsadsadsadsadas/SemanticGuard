// API Configuration
const STRIPE_SECRET_KEY = "sk_live_EXAMPLE_KEY_NOT_REAL_12345678";
const OPENAI_API_KEY = "sk-proj-EXAMPLE_KEY_NOT_REAL_ABCDEFGH";
const DATABASE_URL = "postgresql://admin:password123@db.example.com:5432/prod";

export function initializePayment() {
    const stripe = require('stripe')(STRIPE_SECRET_KEY);
    return stripe;
}
