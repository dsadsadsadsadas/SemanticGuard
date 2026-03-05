/**
 * Test script for AI Autonomy Fallback Heuristics
 * 
 * Tests the keyword-based heuristics that work when the model
 * doesn't generate [AI_ASSISTANT_ACTIONS] section.
 */

// Test responses WITHOUT [AI_ASSISTANT_ACTIONS]

const testResponse1_RuleViolation = {
    thought: `
[THOUGHT]
The incoming code violates system_rules.md Rule #3 which states
"NEVER use async/await in synchronous Flask routes". This is
forbidden because Flask is not async-native and will cause runtime errors.
    `.trim(),
    verdict: 'REJECT',
    score: 0.85
};

const testResponse2_Error = {
    thought: `
[THOUGHT]
The code has a critical error in the database connection logic.
The connection string is malformed and will fail at runtime.
This doesn't work because the port number is missing.
    `.trim(),
    verdict: 'REJECT',
    score: 0.65
};

const testResponse3_PatternCompliance = {
    thought: `
[THOUGHT]
The code follows the recommended pattern from golden_state.md
for background tasks using threading.Thread. This is the correct
approach for Flask applications and aligns with our architectural standards.
    `.trim(),
    verdict: 'ACCEPT',
    score: 0.05
};

const testResponse4_NoTriggers = {
    thought: `
[THOUGHT]
The code is acceptable but could be improved. Consider adding
more comments and better variable names.
    `.trim(),
    verdict: 'ACCEPT',
    score: 0.25
};

function testHeuristic(response, testName) {
    console.log(`\n${'='.repeat(70)}`);
    console.log(`TEST: ${testName}`);
    console.log('='.repeat(70));
    console.log(`Verdict: ${response.verdict}`);
    console.log(`Score: ${response.score}`);
    console.log(`Thought: ${response.thought.substring(0, 100)}...`);
    console.log();

    const thought = response.thought.toLowerCase();
    let triggered = false;

    // HEURISTIC 1: Rule Violation Detection
    if (response.verdict === 'REJECT' && response.score >= 0.40) {
        const violationKeywords = ['violates', 'breaks', 'forbidden', 'not allowed', 'against rule'];
        if (violationKeywords.some(kw => thought.includes(kw))) {
            console.log('✅ HEURISTIC 1 TRIGGERED: Rule Violation Detection');
            console.log('   Action: Append to problems_and_resolutions.md');
            console.log('   Content: Problem: Rule Violation Detected');
            triggered = true;
        }
    }

    // HEURISTIC 2: Error/Failure Detection
    const errorKeywords = ['error', 'failed', 'doesn\'t work', 'broken', 'issue', 'problem'];
    if (errorKeywords.some(kw => thought.includes(kw))) {
        console.log('✅ HEURISTIC 2 TRIGGERED: Error/Failure Detection');
        console.log('   Action: Append to problems_and_resolutions.md');
        console.log('   Content: Problem: Error Detected');
        triggered = true;
    }

    // HEURISTIC 3: Pattern Compliance Detection
    if (response.verdict === 'ACCEPT' && response.score <= 0.15) {
        const patternKeywords = ['follows pattern', 'correct approach', 'good practice', 'recommended', 'aligns with'];
        if (patternKeywords.some(kw => thought.includes(kw))) {
            console.log('✅ HEURISTIC 3 TRIGGERED: Pattern Compliance Detection');
            console.log('   Action: Append to history_phases.md');
            console.log('   Content: Success: Pattern Followed');
            triggered = true;
        }
    }

    if (!triggered) {
        console.log('⚠️  NO HEURISTICS TRIGGERED');
        console.log('   No automatic pillar updates will be made');
    }

    console.log();
}

// Run tests
console.log('\n🧪 AI AUTONOMY FALLBACK HEURISTICS - TEST SUITE\n');

testHeuristic(testResponse1_RuleViolation, 'Rule Violation (REJECT + High Score + Keywords)');
testHeuristic(testResponse2_Error, 'Error Detection (Error Keywords)');
testHeuristic(testResponse3_PatternCompliance, 'Pattern Compliance (ACCEPT + Low Score + Keywords)');
testHeuristic(testResponse4_NoTriggers, 'No Triggers (Should Skip)');

console.log('='.repeat(70));
console.log('✅ All heuristic tests completed');
console.log('='.repeat(70) + '\n');

// Summary
console.log('SUMMARY:');
console.log('--------');
console.log('Heuristic 1: Rule Violation Detection');
console.log('  Triggers: REJECT + Score >= 0.40 + Keywords');
console.log('  Keywords: violates, breaks, forbidden, not allowed, against rule');
console.log('  Action: Append to problems_and_resolutions.md');
console.log();
console.log('Heuristic 2: Error/Failure Detection');
console.log('  Triggers: Keywords present');
console.log('  Keywords: error, failed, doesn\'t work, broken, issue, problem');
console.log('  Action: Append to problems_and_resolutions.md');
console.log();
console.log('Heuristic 3: Pattern Compliance Detection');
console.log('  Triggers: ACCEPT + Score <= 0.15 + Keywords');
console.log('  Keywords: follows pattern, correct approach, good practice, recommended, aligns with');
console.log('  Action: Append to history_phases.md');
console.log();
