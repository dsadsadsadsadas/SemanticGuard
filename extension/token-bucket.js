/**
 * Token Bucket Rate Limiter
 * 
 * Ported from st/token_bucket.py for production use.
 * Implements precise mathematical rate limiting with:
 * - Dynamic token refill based on elapsed time
 * - Global pause support for 429 errors
 * - Token refund mechanism
 * - Adaptive to account TPM limits
 */

class TokenBucket {
    /**
     * Initialize the token bucket
     * @param {number} maxRpm - Maximum requests per minute
     * @param {number} maxTpm - Maximum tokens per minute (capacity and refill rate)
     */
    constructor(maxRpm = 30, maxTpm = 30000) {
        this.maxRpm = maxRpm;
        this.maxTpm = maxTpm;
        this.capacity = maxTpm;
        this.tokens = maxTpm;
        this.refillRate = maxTpm / 60.0; // Tokens per second
        this.lastRefill = Date.now() / 1000; // Convert to seconds
        this.globalPauseUntil = 0.0;
        this.safetyBuffer = 1.10; // 10% safety margin
        
        // Dynamic max_file_tokens based on TPM
        // For 500k TPM: allow up to 100k tokens per file (20% of capacity)
        // For 30k TPM: allow up to 22k tokens per file (73% of capacity)
        this.maxFileTokens = Math.min(Math.floor(maxTpm * 0.2), 100000);
        
        console.log(`[TOKEN BUCKET] Initialized: ${maxTpm.toLocaleString()} TPM, max file: ${this.maxFileTokens.toLocaleString()} tokens`);
    }
    
    /**
     * Consume tokens from the bucket
     * @param {number} requestedTokens - Number of tokens to consume
     * @returns {Promise<number>} - Wait time in seconds
     */
    async consume(requestedTokens) {
        const now = Date.now() / 1000;
        
        // Step 1: Check if we're in a global pause
        if (now < this.globalPauseUntil) {
            const pauseTime = this.globalPauseUntil - now;
            console.log(`[TOKEN BUCKET] Global pause active, waiting ${pauseTime.toFixed(1)}s`);
            await this.sleep(pauseTime * 1000);
            return pauseTime;
        }
        
        // Step 2: Refill tokens based on elapsed time
        const elapsed = now - this.lastRefill;
        if (elapsed > 0) {
            this.tokens = Math.min(
                this.capacity,
                this.tokens + (elapsed * this.refillRate)
            );
        }
        
        // Step 3: Check if we have enough tokens
        if (this.tokens >= requestedTokens) {
            // We have enough tokens, deduct and return immediately
            this.tokens -= requestedTokens;
            this.lastRefill = now;
            return 0.0;
        }
        
        // Step 4: Calculate deficit and wait time
        const deficit = requestedTokens - this.tokens;
        const waitTime = deficit / this.refillRate;
        
        // Step 5: Set tokens to 0 and keep last_refill at NOW
        this.tokens = 0;
        this.lastRefill = now;
        
        // Step 6: Sleep for the calculated wait time
        console.log(`[TOKEN BUCKET] Waiting ${waitTime.toFixed(2)}s for ${requestedTokens.toLocaleString()} tokens`);
        await this.sleep(waitTime * 1000);
        
        return waitTime;
    }
    
    /**
     * Set global pause when 429 error occurs
     * @param {number} duration - Pause duration in seconds
     */
    async setGlobalPause(duration = 30.0) {
        this.globalPauseUntil = (Date.now() / 1000) + duration;
        console.log(`[TOKEN BUCKET] Global pause set for ${duration}s`);
    }
    
    /**
     * Consume tokens with wait
     * @param {number} fileTokens - Number of tokens for this file
     * @returns {Promise<number>} - Wait time in seconds, or -1 if file too large
     */
    async consumeWithWait(fileTokens) {
        // Check if file is too large
        if (fileTokens > this.maxFileTokens) {
            return -1.0; // Signal to skip this file
        }
        
        // Use the main consume method
        return await this.consume(fileTokens);
    }
    
    /**
     * Refund tokens if estimate was too high
     * @param {number} tokensEstimated - Estimated tokens
     * @param {number} tokensActual - Actual tokens used
     */
    refund(tokensEstimated, tokensActual) {
        if (tokensEstimated > tokensActual) {
            const refundAmount = tokensEstimated - tokensActual;
            this.tokens = Math.min(this.capacity, this.tokens + refundAmount);
            console.log(`[TOKEN BUCKET] Refunded ${refundAmount} tokens`);
        }
    }
    
    /**
     * Sleep helper
     * @param {number} ms - Milliseconds to sleep
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    /**
     * Get current state (for debugging)
     */
    getState() {
        return {
            tokens: Math.floor(this.tokens),
            capacity: this.capacity,
            refillRate: this.refillRate,
            maxFileTokens: this.maxFileTokens
        };
    }
}

/**
 * Detect model TPM/RPM limits from Groq API
 * @param {string} apiKey - Groq API key
 * @param {string} modelName - Model name
 * @returns {Promise<{maxRpm: number, maxTpm: number}>} - Detected limits or defaults
 */
async function detectModelLimits(apiKey, modelName) {
    try {
        console.log(`[TOKEN BUCKET] Detecting model limits from Groq API for model: ${modelName}...`);
        
        // Use built-in fetch (Node 18+) or https module
        const https = require('https');
        
        const postData = JSON.stringify({
            model: modelName,
            messages: [{ role: 'user', content: 'test' }],
            max_tokens: 1
        });
        
        const options = {
            hostname: 'api.groq.com',
            port: 443,
            path: '/openai/v1/chat/completions',
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${apiKey}`,
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            }
        };
        
        const response = await new Promise((resolve, reject) => {
            const req = https.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    resolve({
                        status: res.statusCode,
                        headers: res.headers,
                        body: data
                    });
                });
            });
            
            req.on('error', reject);
            req.write(postData);
            req.end();
        });
        
        console.log(`[TOKEN BUCKET] API Response Status: ${response.status}`);
        
        const headers = response.headers;
        let maxRpm = null;
        let maxTpm = null;
        
        // Log ALL headers for debugging
        console.log('[TOKEN BUCKET] All response headers:');
        for (const [key, value] of Object.entries(headers)) {
            console.log(`  ${key}: ${value}`);
        }
        
        // Search for LIMIT headers (not remaining/used/reset)
        // Groq API returns:
        //   x-ratelimit-limit-requests: 500000 (RPD - Requests Per Day)
        //   x-ratelimit-limit-tokens: 300000 (TPM - Tokens Per Minute)
        // Note: There is NO x-ratelimit-limit-requests-minute header in the actual API response!
        let rpdValue = null; // Requests Per Day (fallback if no RPM)
        
        for (const [key, value] of Object.entries(headers)) {
            const keyLower = key.toLowerCase();
            
            // Skip remaining, used, reset headers
            if (keyLower.includes('remaining') || 
                keyLower.includes('used') || 
                keyLower.includes('reset')) {
                console.log(`  [SKIP] ${key} (not a limit header)`);
                continue;
            }
            
            // Look for RPM limit: must have "ratelimit", "request", "limit", AND "minute"
            // This header does NOT exist in Groq API, but we check for it anyway
            if (keyLower.includes('ratelimit') && 
                keyLower.includes('request') && 
                keyLower.includes('limit') &&
                keyLower.includes('minute')) {
                const parsed = parseInt(value);
                if (!isNaN(parsed) && parsed > 0) {
                    maxRpm = parsed;
                    console.log(`[TOKEN BUCKET] ✓ Found RPM LIMIT: ${key} = ${maxRpm.toLocaleString()}`);
                }
            }
            
            // Look for RPD header (Requests Per Day) for fallback estimation
            // This is what Groq actually returns: x-ratelimit-limit-requests
            if (keyLower.includes('ratelimit') && 
                keyLower.includes('request') && 
                keyLower.includes('limit') &&
                !keyLower.includes('minute')) {
                const parsed = parseInt(value);
                if (!isNaN(parsed) && parsed > 0) {
                    rpdValue = parsed;
                    console.log(`[TOKEN BUCKET] Found RPD (Requests Per Day): ${key} = ${rpdValue.toLocaleString()}`);
                }
            }
            
            // Look for TPM limit: must have "ratelimit", "token", and "limit"
            // This is what Groq returns: x-ratelimit-limit-tokens
            if (keyLower.includes('ratelimit') && 
                keyLower.includes('token') && 
                keyLower.includes('limit')) {
                
                // Skip if it's per-day or per-hour
                if (keyLower.includes('day') || keyLower.includes('hour')) {
                    console.log(`  [SKIP] ${key} (per-day or per-hour, not per-minute)`);
                } else {
                    const parsed = parseInt(value);
                    if (!isNaN(parsed) && parsed > 0) {
                        maxTpm = parsed;
                        console.log(`[TOKEN BUCKET] ✓ Found TPM LIMIT: ${key} = ${maxTpm.toLocaleString()}`);
                    }
                }
            }
        }
        
        // CRITICAL: If no RPM header found (which is the case for Groq), estimate from RPD
        // This matches the Python logic in st/stress_test.py lines 975-980
        if (!maxRpm && rpdValue) {
            maxRpm = Math.floor(rpdValue / 1440); // RPD / minutes per day
            console.log(`[TOKEN BUCKET] ⚠️ No RPM header found, estimated from RPD: ${maxRpm} RPM (${rpdValue.toLocaleString()} RPD / 1440 minutes)`);
        }
        
        if (maxRpm && maxTpm) {
            console.log(`[TOKEN BUCKET] ✓ Detected from API: ${maxRpm} RPM, ${maxTpm.toLocaleString()} TPM`);
            
            if (maxTpm >= 500000) {
                console.log(`[TOKEN BUCKET] >>> UPGRADED ACCOUNT! You have ${maxTpm.toLocaleString()} TPM`);
            }
            
            return { maxRpm, maxTpm };
        } else {
            console.log(`[TOKEN BUCKET] ⚠️ Could not detect limits from headers, using defaults`);
            console.log(`[TOKEN BUCKET] Found: maxRpm=${maxRpm}, maxTpm=${maxTpm}`);
            return { maxRpm: 30, maxTpm: 30000 };
        }
        
    } catch (error) {
        console.log(`[TOKEN BUCKET] API detection failed: ${error.message}`);
        return { maxRpm: 30, maxTpm: 30000 };
    }
}

module.exports = {
    TokenBucket,
    detectModelLimits
};
