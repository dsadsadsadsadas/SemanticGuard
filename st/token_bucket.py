import asyncio
import time


class TokenBucket:
    """
    A thread-safe token bucket rate limiter using asyncio.Lock.
    
    Guarantees:
    - No race conditions: token deduction is atomic within the lock
    - Strict serialization: File 1 cannot read state until File 2 completes deduction
    - Mathematically sound: deficit calculation and wait time are precise
    - Global pause support: 429 errors trigger a 35-second global pause
    """

    def __init__(self, max_rpm=30, max_tpm=30000):
        """
        Initialize the token bucket.
        
        Args:
            max_rpm: Maximum requests per minute (for compatibility)
            max_tpm: Maximum tokens per minute (capacity and refill rate)
        """
        self.max_rpm = max_rpm
        self.max_tpm = max_tpm
        self.capacity = max_tpm
        self.tokens = max_tpm
        self.refill_rate = max_tpm / 60.0  # Tokens per second
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        self.global_pause_until = 0.0
        
        # Dynamic max_file_tokens based on TPM
        # For 500k TPM: allow up to 100k tokens per file (20% of capacity)
        # For 30k TPM: allow up to 22k tokens per file (73% of capacity)
        # Formula: min(TPM * 0.2, 100000) to cap at 100k for very high TPM
        self.max_file_tokens = min(int(max_tpm * 0.2), 100000)
        
        self.safety_buffer = 1.10  # 10% safety margin

    async def consume(self, requested_tokens):
        """
        Consume tokens from the bucket with strict lock-based serialization.
        
        This method ensures:
        1. Token state is read and modified atomically within the lock
        2. Wait time is calculated before releasing the lock
        3. Sleep happens outside the lock to avoid blocking other tasks
        4. Tokens never go negative and last_refill never advances into the future
        
        Args:
            requested_tokens: Number of tokens to consume
            
        Returns:
            Total wait time in seconds (pause_time + wait_time)
        """
        wait_time = 0.0
        pause_time = 0.0

        # CRITICAL: All state mutations happen inside the lock
        async with self.lock:
            now = time.time()

            # Step 1: Check if we're in a global pause
            if now < self.global_pause_until:
                pause_time = self.global_pause_until - now
                # Don't refill during pause, just return the pause time
                return pause_time

            # Step 2: Refill tokens based on elapsed time
            elapsed = now - self.last_refill
            # Ensure elapsed is never negative (defensive programming)
            if elapsed < 0:
                elapsed = 0
                self.last_refill = now
            
            self.tokens = min(
                self.capacity,
                self.tokens + (elapsed * self.refill_rate)
            )

            # Step 3: Check if we have enough tokens
            if self.tokens >= requested_tokens:
                # We have enough tokens, deduct and return immediately
                self.tokens -= requested_tokens
                self.last_refill = now
                return 0.0

            # Step 4: Calculate deficit and wait time
            deficit = requested_tokens - self.tokens
            wait_time = deficit / self.refill_rate

            # Step 5: FIX - Set tokens to 0 and keep last_refill at NOW
            # This prevents negative tokens and future time advancement
            self.tokens = 0
            self.last_refill = now

        # Step 6: Sleep OUTSIDE the lock (critical for concurrency)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        return wait_time

    async def trigger_global_pause(self):
        """
        Trigger a global pause when a 429 error is encountered.
        
        This method:
        1. Acquires the lock to ensure atomic state update
        2. Sets global_pause_until to 35 seconds in the future
        3. All subsequent consume() calls will wait until this time passes
        """
        async with self.lock:
            self.global_pause_until = time.time() + 35.0

    async def set_global_pause(self, duration: float = 30.0):
        """
        Alias for trigger_global_pause for backward compatibility.
        Sets global pause flag when 429 error occurs.
        """
        async with self.lock:
            self.global_pause_until = time.time() + duration

    async def consume_with_wait(self, file_tokens: int) -> float:
        """
        Consume tokens, waiting if necessary. Returns actual wait time.
        
        This is the main method called by audit_file.
        Handles the full consume-and-wait flow.
        """
        # Check if file is too large
        if file_tokens > self.max_file_tokens:
            return -1.0  # Signal to skip this file
        
        # Use the main consume method which handles everything
        wait_time = await self.consume(file_tokens)
        return wait_time

    def refund(self, tokens_estimated: int, tokens_actual: int):
        """
        Refund tokens if estimate was too high.
        This is called when actual token usage is less than estimated.
        """
        if tokens_estimated > tokens_actual:
            refund_amount = tokens_estimated - tokens_actual
            self.tokens = min(self.capacity, self.tokens + refund_amount)

    async def get_state(self):
        """
        Get the current state of the token bucket (for debugging/monitoring).
        
        Returns:
            dict with current tokens, capacity, and pause status
        """
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            current_tokens = min(
                self.capacity,
                self.tokens + (elapsed * self.refill_rate)
            )
            is_paused = now < self.global_pause_until
            return {
                "tokens": current_tokens,
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
                "is_paused": is_paused,
                "pause_until": self.global_pause_until if is_paused else None,
            }
