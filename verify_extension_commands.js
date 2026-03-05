/**
 * Trepan Extension Command Verification Script
 * 
 * Run this in VS Code Developer Console to verify all Trepan commands are registered.
 * 
 * How to use:
 * 1. Open VS Code
 * 2. Press Ctrl+Shift+P
 * 3. Run: "Developer: Toggle Developer Tools"
 * 4. Go to Console tab
 * 5. Copy and paste this entire script
 * 6. Press Enter
 */

(async function verifyTrepanCommands() {
    console.log('🛡️ Trepan Extension Command Verification');
    console.log('==========================================\n');

    // Expected commands from package.json
    const expectedCommands = [
        'trepan.status',
        'trepan.toggleEnabled',
        'trepan.askGatekeeper',
        'trepan.openLedger',
        'trepan.reviewWithLedger',
        'trepan.initializeProject'  // The missing command
    ];

    try {
        // Get all registered commands
        const allCommands = await vscode.commands.getCommands();
        const trepanCommands = allCommands.filter(c => c.startsWith('trepan.'));

        console.log('📋 Registered Trepan Commands:');
        console.log('------------------------------');
        
        if (trepanCommands.length === 0) {
            console.error('❌ NO Trepan commands found!');
            console.error('   The extension may not be activated.');
            console.error('   Check for activation errors above.');
            return;
        }

        trepanCommands.forEach(cmd => {
            console.log(`  ✅ ${cmd}`);
        });

        console.log('\n🔍 Verification Results:');
        console.log('------------------------');

        let allPresent = true;
        expectedCommands.forEach(expected => {
            const isPresent = trepanCommands.includes(expected);
            if (isPresent) {
                console.log(`  ✅ ${expected} - REGISTERED`);
            } else {
                console.error(`  ❌ ${expected} - MISSING`);
                allPresent = false;
            }
        });

        console.log('\n📊 Summary:');
        console.log('-----------');
        console.log(`  Expected: ${expectedCommands.length} commands`);
        console.log(`  Found: ${trepanCommands.length} commands`);
        console.log(`  Status: ${allPresent ? '✅ ALL COMMANDS REGISTERED' : '❌ SOME COMMANDS MISSING'}`);

        if (!allPresent) {
            console.log('\n🔧 Troubleshooting:');
            console.log('-------------------');
            console.log('  1. Check for activation errors in the console above');
            console.log('  2. Reload VS Code window: Ctrl+Shift+P -> "Developer: Reload Window"');
            console.log('  3. Check if extension is enabled: Ctrl+Shift+X -> Search "Trepan"');
            console.log('  4. Check extension.js for registration errors');
        } else {
            console.log('\n✅ All commands are registered correctly!');
            console.log('   If you still can\'t see "Trepan: Initialize Project" in the palette:');
            console.log('   1. Try reloading the window: Ctrl+Shift+P -> "Developer: Reload Window"');
            console.log('   2. Clear the command palette cache by restarting VS Code');
        }

        // Check if the specific command can be executed
        console.log('\n🧪 Testing Command Execution:');
        console.log('-----------------------------');
        
        const canExecute = trepanCommands.includes('trepan.initializeProject');
        if (canExecute) {
            console.log('  ✅ trepan.initializeProject is registered and should be executable');
            console.log('  Try running it: Ctrl+Shift+P -> Type "Trepan Ini"');
        } else {
            console.error('  ❌ trepan.initializeProject is NOT registered');
            console.error('  The extension needs to be reloaded or there was an activation error');
        }

    } catch (error) {
        console.error('❌ Error during verification:', error);
        console.error('   Make sure you\'re running this in VS Code Developer Console');
    }

    console.log('\n==========================================');
    console.log('Verification complete!');
})();
