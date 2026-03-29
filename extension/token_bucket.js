/**
 * Token Bucket Rate Limiter (JavaScript Port)
 * 
 * Ported from st/token_bucket.py for client-side rate limiting.
 * Implements the same mathematical deficit calculation as stress_test.py.
 * 
 * Key Features:
 * - Continuous token refill at refill_rate = max_tpm / 60.0 tokens/second
 * - Mathematical deficit calculation: wait_time = deficit / refill_rate
 * - Token refunds for overestimates
 * - Global pause support for 429 errors
 */

class TokenBucket {
    /**
     * Initialize the token bucket.
     * 
     * @param {number} maxRpm - Maximum requests per minute
     * @param {number} maxTpm - Maximum tokens per minute (capacity and refill rate)
     */
    constructor(maxRpm = 30, maxTpm = 30000) {
        this.maxRpm = maxRpm;
        this.maxTpm = maxTpm;
        this.capacity = maxTpm;
        this.tokens = maxTpm;
        this.refillRate = maxTpm / 60.0;  // Tokens per second
        this.lastRefill = Date.now() / 1000;  // Convert to seconds
        this.globalPauseUntil = 0.0;
        
        // Dynamic max_file_tokens based on TPM
        // For 500k TPM: allow up to 100k tokens per file (20% of capacity)
        // For 30k TPM: allow up to 6k tokens per file (20% of capacity)
        this.maxFileTokens = Math.min(Math.floor(maxTpm * 0.2), 100000);
        
        this.safetyBuffer = 1.10;  // 10% safety margin
        
        console.log(`[TOKEN BUCKET] Initialized: ${maxTpm.toLocaleString()} TPM, ${maxRpm} RPM`);
        console.log(`[TOKEN BUCKET] Refill rate: ${this.refillRate.toFixed(2)} tokens/second`);
        console.log(`[TOKEN BUCKET] Max file size: ${this.maxFileTokens.toLocaleString()} tokens`);
    }

    /**
     * Consume tokens from the bucket with mathematical deficit calculation.
     * 
     * @param {number} requestedTokens - Number of tokens to consume
     * @returns {Promise<number>} - Total wait time in seconds
     */
    async consume(requestedTokens) {
        const now = Date.now() / 1000;  // Convert to seconds
        
        // Step 1: Check if we're in a global pause
        if (now < this.globalPauseUntil) {
            const pauseTime = this.globalPauseUntil - now;
            console.log(`[TOKEN BUCKET] Global pause active, waiting ${pauseTime.toFixed(2)}s`);
            await this.sleep(pauseTime * 1000);  // Convert to milliseconds
            return pauseTime;
        }

        // Step 2: Refill tokens based on elapsed time
        const elapsed = now - this.lastRefill;
        this.tokens = Math.min(
            this.capacity,
            this.tokens + (elapsed * this.refillRate)
        );

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

        console.log(`[TOKEN BUCKET] Deficit: ${deficit.toFixed(0)} tokens, waiting ${waitTime.toFixed(2)}s`);

        // Step 5: Set tokens to 0 and keep last_refill at NOW
        this.tokens = 0;
        this.lastRefill = now;

        // Step 6: Sleep for the calculated wait time
        await this.sleep(waitTime * 1000);  // Convert to milliseconds

        return waitTime;
    }

    /**
     * Consume tokens with wait, checking file size limits.
     * 
     * @param {number} fileTokens - Number of tokens to consume
     * @returns {Promise<number>} - Wait time in seconds, or -1 if file too large
     */
    async consumeWithWait(fileTokens) {
        // Check if file is too large
        if (fileTokens > this.maxFileTokens) {
            return -1.0;  // Signal to skip this file
        }
        
        return await this.consume(fileTokens);
    }

    /**
     * Refund tokens if estimate was too high.
     * 
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
     * Set global pause when 429 error occurs.
     * 
     * @param {number} duration - Pause duration in seconds
     */
    async setGlobalPause(duration = 30.0) {
        this.globalPauseUntil = (Date.now() / 1000) + duration;
        console.log(`[TOKEN BUCKET] Global pause set for ${duration}s`);
    }

    /**
     * Get current state of the token bucket.
     * 
     * @returns {Object} - Current state
     */
    getState() {
        const now = Date.now() / 1000;
        const elapsed = now - this.lastRefill;
        const currentTokens = Math.min(
            this.capacity,
            this.tokens + (elapsed * this.refillRate)
        );
        const isPaused = now < this.globalPauseUntil;
        
        return {
            tokens: currentTokens,
            capacity: this.capacity,
            refillRate: this.refillRate,
            isPaused: isPaused,
            pauseUntil: isPaused ? this.globalPauseUntil : null
        };
    }

    /**
     * Sleep helper function.
     * 
     * @param {number} ms - Milliseconds to sleep
     * @returns {Promise<void>}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

module.exports = { TokenBucket };
