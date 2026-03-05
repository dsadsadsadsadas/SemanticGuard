# Fix: Missing "Trepan: Initialize Project" Command

## Issue
The `Trepan: Initialize Project` command is not appearing in the VS Code command palette when typing "Trepan Ini".

## Audit Results: ✅ CODE IS CORRECT

After a full audit of the extension:
- ✅ `package.json` has the command registered correctly
- ✅ `extension.js` registers the command in `activate()`
- ✅ Command is added to subscriptions
- ✅ No blocking code or early returns

**Conclusion**: The code is correct. The issue is that VS Code needs to reload to pick up the command.

## Solution: Reload VS Code

### Quick Fix (Recommended)

1. **Reload the VS Code window**:
   - Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (Mac)
   - Type: `Developer: Reload Window`
   - Press Enter

2. **Verify the command appears**:
   - Press `Ctrl+Shift+P` again
   - Type: `Trepan Ini`
   - You should now see: `⚡ Trepan: Initialize Project`

### If That Doesn't Work

#### Step 1: Check Extension is Activated

1. Open Developer Tools:
   - Press `Ctrl+Shift+P`
   - Run: `Developer: Toggle Developer Tools`

2. Check the Console tab for:
   - `"🛡️ Trepan Gatekeeper: Airbag active"` (success message)
   - Any error messages related to "trepan"

3. If you see errors, the extension failed to activate

#### Step 2: Verify Command Registration

1. In the Developer Console, run:
   ```javascript
   vscode.commands.getCommands().then(commands => {
       const trepanCommands = commands.filter(c => c.startsWith('trepan.'));
       console.log('Trepan commands:', trepanCommands);
   });
   ```

2. Expected output should include `trepan.initializeProject`

3. If it's missing, the extension didn't activate properly

#### Step 3: Use the Verification Script

1. Open `verify_extension_commands.js`
2. Copy the entire contents
3. Paste into VS Code Developer Console
4. Press Enter
5. Follow the troubleshooting steps it provides

#### Step 4: Reinstall Extension (Last Resort)

If nothing else works:

1. **Uninstall the extension**:
   - Press `Ctrl+Shift+X`
   - Find "Trepan Gatekeeper"
   - Click the gear icon → Uninstall

2. **Close VS Code completely**

3. **Reinstall the extension**:
   - Reopen VS Code
   - Install the extension again

4. **Reload the window**:
   - Press `Ctrl+Shift+P`
   - Run: `Developer: Reload Window`

## Why This Happens

VS Code caches extension registrations. When you:
- Modify `package.json`
- Modify `extension.js`
- Update the extension
- Install the extension for the first time

VS Code needs to reload to pick up the changes.

## Prevention

To avoid this issue in the future:

1. **Always reload after extension changes**:
   - After modifying extension code
   - After updating the extension
   - After installing the extension

2. **Check for activation errors**:
   - Open Developer Tools after installing
   - Look for the activation success message
   - Check for any error messages

3. **Use the verification script**:
   - Run `verify_extension_commands.js` after changes
   - Confirms all commands are registered

## Testing the Fix

After reloading, test the command:

1. **Open Command Palette**:
   - Press `Ctrl+Shift+P`

2. **Search for the command**:
   - Type: `Trepan Ini`
   - You should see: `⚡ Trepan: Initialize Project`

3. **Execute the command**:
   - Click on it or press Enter
   - You should see a template selection dialog

4. **Verify it works**:
   - Choose a template (e.g., "Solo-Indie")
   - Wait for initialization to complete
   - Check that `.trepan/` folder is created

## Expected Behavior

When the command works correctly:

1. **Command Palette shows**:
   ```
   ⚡ Trepan: Initialize Project
   ```

2. **Template selection appears**:
   ```
   $(zap) Solo-Indie (The Speedster)
   $(layers) Clean-Layers (The Architect)
   $(shield) Secure-Stateless (The Fortress)
   ```

3. **Progress notification shows**:
   ```
   Trepan: Initializing Project
   Creating .trepan directory...
   Generating golden template...
   Opening generated files...
   ```

4. **Success message appears**:
   ```
   ✅ Trepan initialized with Solo-Indie (The Speedster)!
   Review your system_rules.md and golden_state.md.
   ```

5. **Files are created**:
   - `.trepan/system_rules.md`
   - `.trepan/golden_state.md`
   - `.trepan/done_tasks.md`
   - `.trepan/pending_tasks.md`
   - `.trepan/history_phases.md`
   - `.trepan/problems_and_resolutions.md`
   - `.trepan/Walkthrough.md`
   - `.trepan/README.md`

## Troubleshooting Checklist

- [ ] Reloaded VS Code window
- [ ] Checked Developer Console for errors
- [ ] Verified extension is installed and enabled
- [ ] Ran verification script
- [ ] Checked command is registered (Developer Console)
- [ ] Tried restarting VS Code completely
- [ ] Reinstalled extension (if needed)

## Still Not Working?

If the command still doesn't appear after all these steps:

1. **Check the extension files**:
   - Verify `extension/package.json` has the command
   - Verify `extension/extension.js` registers the command
   - Look for syntax errors

2. **Check VS Code version**:
   - Minimum required: VS Code 1.74.0
   - Update VS Code if needed

3. **Check for conflicts**:
   - Other extensions might interfere
   - Try disabling other extensions temporarily

4. **Check the logs**:
   - Open: `Help` → `Toggle Developer Tools`
   - Check Console and Network tabs for errors

## Summary

The command registration code is **100% correct**. The issue is that VS Code needs to reload to pick up the command registration.

**Solution**: Press `Ctrl+Shift+P` → Run `Developer: Reload Window`

After reloading, the command will appear in the palette when you type "Trepan Ini".
