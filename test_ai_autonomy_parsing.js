/**
 * Test script for AI Assistant Autonomy action parsing
 * 
 * This tests the regex patterns used in executeAIAssistantActions()
 * to ensure they correctly parse [AI_ASSISTANT_ACTIONS] sections.
 */

// Test LLM response with AI_ASSISTANT_ACTIONS
const testResponse1 = `
[THOUGHT]
The incoming code uses async/await in a Flask route. This violates system_rules.md Rule #3.

[AI_ASSISTANT_ACTIONS]
APPEND_TO_FILE: .trepan/problems_and_resolutions.md
CONTENT: |
  ## Problem #7: Async/await in Flask (UNRESOLVED)
  **Date**: 2026-03-04
  **AI Generated**: Yes
  **Description**: Tried to use async/await in Flask route
  **Status**: UNRESOLVED

APPEND_TO_FILE: .trepan/system_rules.md
CONTENT: |
  ## AI-Learned Rule #8
  **NEVER** use async/await in synchronous Flask routes
  **Learned**: 2026-03-04

[SCORE]
0.85

[ACTION]
REJECT
`;

// Test response without AI_ASSISTANT_ACTIONS
const testResponse2 = `
[THOUGHT]
Code looks good, follows all rules.

[SCORE]
0.05

[ACTION]
ACCEPT
`;

// Test response with single action
const testResponse3 = `
[THOUGHT]
Task completed successfully.

[AI_ASSISTANT_ACTIONS]
APPEND_TO_FILE: .trepan/history_phases.md
CONTENT: |
  ## AI Task: 2026-03-04
  **Completed**: Implemented authentication
  **Outcome**: Working JWT system

[SCORE]
0.10

[ACTION]
ACCEPT
`;

function testActionParsing(response, testName) {
    console.log(`\n${'='.repeat(60)}`);
    console.log(`TEST: ${testName}`);
    console.log('='.repeat(60));

    // Extract [AI_ASSISTANT_ACTIONS] section
    const actionsMatch = response.match(/\[AI_ASSISTANT_ACTIONS\]([\s\S]*?)(?:\[|$)/);
    
    if (!actionsMatch) {
        console.log('❌ No [AI_ASSISTANT_ACTIONS] section found');
        return;
    }

    const actionsSection = actionsMatch[1].trim();
    console.log('✅ Found actions section:');
    console.log(actionsSection.substring(0, 100) + '...\n');

    // Parse APPEND_TO_FILE commands
    const appendCommands = actionsSection.matchAll(/APPEND_TO_FILE:\s*(.+?)\nCONTENT:\s*\|?\n([\s\S]*?)(?=\n\nAPPEND_TO_FILE:|$)/g);
    
    let commandCount = 0;
    for (const match of appendCommands) {
        commandCount++;
        const filePath = match[1].trim();
        const content = match[2].trim();
        
        console.log(`Command #${commandCount}:`);
        console.log(`  File: ${filePath}`);
        console.log(`  Content length: ${content.length} chars`);
        console.log(`  Content preview: ${content.substring(0, 80)}...`);
        console.log();
    }

    if (commandCount === 0) {
        console.log('⚠️  No APPEND_TO_FILE commands found in actions section');
    } else {
        console.log(`✅ Successfully parsed ${commandCount} command(s)`);
    }
}

// Run tests
console.log('\n🧪 AI ASSISTANT AUTONOMY - ACTION PARSING TESTS\n');

testActionParsing(testResponse1, 'Multiple Actions (Problem + Rule)');
testActionParsing(testResponse2, 'No Actions Section');
testActionParsing(testResponse3, 'Single Action (History Update)');

console.log('\n' + '='.repeat(60));
console.log('✅ All parsing tests completed');
console.log('='.repeat(60) + '\n');
