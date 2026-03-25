#!/usr/bin/env python3
"""
Token Bucket Debug Script
Simulates the bug to understand the exponential wait time issue
"""

import asyncio
import time


class TokenBucketBuggy:
    """Original buggy implementation"""
    def __init__(self, max_tpm=30000):
        self.max_tpm = max_tpm
        self.capacity = max_tpm
        self.tokens = max_tpm
        self.refill_rate = max_tpm / 60.0
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        self.max_file_tokens = int(max_tpm * 0.2)

    async def consume(self, requested_tokens):
        wait_time = 0.0
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))

            if self.tokens >= requested_tokens:
                self.tokens -= requested_tokens
                self.last_refill = now
                return 0.0

            deficit = requested_tokens - self.tokens
            wait_time = deficit / self.refill_rate

            # BUG: This causes exponential wait times
            self.tokens -= requested_tokens  # Can go negative
            self.last_refill = now + wait_time  # ❌ Advances time into future

        if wait_time > 0:
            await asyncio.sleep(wait_time)
        return wait_time


class TokenBucketFixed:
    """Fixed implementation"""
    def __init__(self, max_tpm=30000):
        self.max_tpm = max_tpm
        self.capacity = max_tpm
        self.tokens = max_tpm
        self.refill_rate = max_tpm / 60.0
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
        self.max_file_tokens = int(max_tpm * 0.2)

    async def consume(self, requested_tokens):
        wait_time = 0.0
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))

            if self.tokens >= requested_tokens:
                self.tokens -= requested_tokens
                self.last_refill = now
                return 0.0

            deficit = requested_tokens - self.tokens
            wait_time = deficit / self.refill_rate

            # FIX: Deduct tokens and update last_refill to NOW (not future)
            self.tokens = 0  # ✅ Set to 0 instead of going negative
            self.last_refill = now  # ✅ Keep at current time

        if wait_time > 0:
            await asyncio.sleep(wait_time)
        return wait_time


async def simulate_bug():
    """Simulate the bug with 5 files"""
    print("=" * 60)
    print("BUGGY IMPLEMENTATION (Original)")
    print("=" * 60)
    
    bucket = TokenBucketBuggy(max_tpm=30000)
    
    # Simulate 5 files with 8,000 tokens each
    for i in range(1, 6):
        tokens_needed = 8000
        wait_time = await bucket.consume(tokens_needed)
        
        print(f"File {i}: {tokens_needed:,} tokens | Wait: {wait_time:.2f}s | Bucket tokens: {bucket.tokens:.0f}")


async def simulate_fix():
    """Simulate the fix with 5 files"""
    print("\n" + "=" * 60)
    print("FIXED IMPLEMENTATION")
    print("=" * 60)
    
    bucket = TokenBucketFixed(max_tpm=30000)
    
    # Simulate 5 files with 8,000 tokens each
    for i in range(1, 6):
        tokens_needed = 8000
        wait_time = await bucket.consume(tokens_needed)
        
        print(f"File {i}: {tokens_needed:,} tokens | Wait: {wait_time:.2f}s | Bucket tokens: {bucket.tokens:.0f}")


async def main():
    print("\n🐛 Token Bucket Bug Demonstration\n")
    print("Simulating 5 files with 8,000 tokens each")
    print("Max TPM: 30,000 (refill rate: 500 tokens/sec)\n")
    
    await simulate_bug()
    await simulate_fix()
    
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    print("Buggy version: Wait times increase exponentially")
    print("Fixed version: Wait times are consistent and predictable")


if __name__ == "__main__":
    asyncio.run(main())
