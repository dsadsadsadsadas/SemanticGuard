#!/usr/bin/env python3
"""
Test the actual TokenBucket fix
"""

import asyncio
from token_bucket import TokenBucket


async def test_fixed_bucket():
    """Test the fixed TokenBucket implementation"""
    print("=" * 60)
    print("TESTING FIXED TokenBucket (Actual Implementation)")
    print("=" * 60)
    
    bucket = TokenBucket(max_rpm=30, max_tpm=30000)
    
    # Simulate 5 files with 8,000 tokens each
    for i in range(1, 6):
        tokens_needed = 8000
        wait_time = await bucket.consume(tokens_needed)
        
        print(f"File {i}: {tokens_needed:,} tokens | Wait: {wait_time:.2f}s | Bucket tokens: {bucket.tokens:.0f}")
    
    print("\n" + "=" * 60)
    print("RESULT: Wait times should be consistent, not exponential")
    print("Expected: File 4 ~4s, File 5 ~12s (not 20s+)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_fixed_bucket())
