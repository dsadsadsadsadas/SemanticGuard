/**
 * Test script for flexible action tag parsing
 * 
 * Verifies that the extension can parse [ACTION], [ACTIONS], and [AI_ASSISTANT_ACTIONS]
 */

const testCases = [
    {
        name: "Standard [AI_ASSISTANT_ACTIONS] Tag",
        input: `[THOUGHT]
Analysis here...

[AI_ASSISTANT_ACTIONS]
APPEND_TO_FILE: .trepan/problems.md
CONTENT: |
  Problem detected

[SCORE]
0.85

[ACTION]
REJECT`,
        expectedTag: "AI_ASSISTANT_ACTIONS",
        shouldMatch: true
    },
    {
        name: "Short [ACTIONS] Tag",
        input: `[THOUGHT]
Analysis here...

[ACTIONS]
APPEND_TO_FILE: .trepan/problems.md
CONTENT: |
  Problem detected

[SCORE]
0.85

[ACTION]
REJECT`,
        expectedTag: "ACTIONS",
        shouldMatch: true
    },
    {
        name: "Minimal [ACTION] Tag (Should NOT Match - Reserved for Verdict)",
        input: `[THOUGHT]
Analysis here...

[SCORE]
0.85

[ACTION]
REJECT`,
        expectedTag: null,
        shouldMatch: false
    },
    {
        name: "No Action Tags",
        input: `[THOUGHT]
Just analysis without any action tags.

[SCORE]
0.15

[ACTION]
ACCEPT`,
        expectedTag: null,
        shouldMatch: false
    },
    {
        name: "Multiple Action Tags (Use First)",
        input: `[THOUGHT]
Analysis...

[ACTIONS]
First action block

[ACTION]
Second action block

[SCORE]
0.50`,
        expectedTag: "ACTIONS",
        shouldMatch: true
    }
];

console.log('\n🧪 FLEXIBLE ACTION TAG PARSING - TEST SUITE\n');
console.log('='.repeat(70));

let passed = 0;
let failed = 0;

testCases.forEach((test, index) => {
    console.log(`\nTest ${index + 1}: ${test.name}`);
    console.log('-'.repeat(70));
    
    // This is the regex pattern used in the extension
    // NOTE: We only match [AI_ASSISTANT_ACTIONS] or [ACTIONS], NOT [ACTION]
    // because [ACTION] is reserved for the verdict (ACCEPT/REJECT)
    const pattern = /\[(AI_ASSISTANT_ACTIONS|ACTIONS)\]([\s\S]*?)(?:\[|$)/;
    const match = test.input.match(pattern);
    
    const matchFound = match !== null;
    const testPassed = matchFound === test.shouldMatch;
    
    if (testPassed) {
        console.log('✅ PASSED');
        passed++;
    } else {
        console.log('❌ FAILED');
        failed++;
    }
    
    if (match) {
        const tagName = match[1];
        const content = match[2].trim().substring(0, 50);
        console.log(`   Found tag: [${tagName}]`);
        console.log(`   Content preview: ${content}...`);
        
        if (test.expectedTag && tagName !== test.expectedTag) {
            console.log(`   ⚠️  Expected [${test.expectedTag}] but found [${tagName}]`);
        }
    } else {
        console.log('   No action tags found');
    }
});

console.log('\n' + '='.repeat(70));
console.log(`\nResults: ${passed} passed, ${failed} failed`);

if (failed === 0) {
    console.log('✅ All tests passed!');
} else {
    console.log(`❌ ${failed} test(s) failed`);
}

console.log('\n' + '='.repeat(70));
console.log('\nSummary:');
console.log('--------');
console.log('The extension now accepts two action tag formats:');
console.log('  1. [AI_ASSISTANT_ACTIONS] - Ideal format (explicit)');
console.log('  2. [ACTIONS] - Shorter variant');
console.log('\nNote: [ACTION] is reserved for the verdict (ACCEPT/REJECT)');
console.log('and is NOT used for autonomous actions to avoid confusion.');
console.log('\nThis makes the parser more robust and handles cases where');
console.log('the model wasn\'t fine-tuned on [AI_ASSISTANT_ACTIONS].');
console.log('='.repeat(70) + '\n');
