import os
import shutil

TRASH_DIR = "trash"
TO_REMOVE = [
    "auth_handler.py",
    "ast_engine.py",
    "ai_trace.txt",
    "test_vuln.js",
    "test_taint.txt",
    "manual_test.py"
]

if not os.path.exists(TRASH_DIR):
    os.makedirs(TRASH_DIR)
    print(f"📁 Created {TRASH_DIR}")

print("🧹 STARTING CLEANUP...")
for file in TO_REMOVE:
    if os.path.exists(file):
        shutil.move(file, os.path.join(TRASH_DIR, file))
        print(f"   🗑️ Moved to trash: {file}")
    else:
        print(f"   ⚠️ Not found: {file}")

print("\n✅ CLEANUP COMPLETE. Verify 'trash/' folder before deleting.")