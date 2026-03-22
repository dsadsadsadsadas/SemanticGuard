/**
 * Live Test 4: Layer 2 should catch this
 * Expected: [LAYER 2 — FOCUSED ANALYSIS]
 * Layer 1: No deterministic violations
 * Layer 2: userId from req.body reaches console.log() without sanitization
 */

function handleRequest(req) {
    const userId = req.body.userId;
    console.log(userId);
    return "OK";
}
