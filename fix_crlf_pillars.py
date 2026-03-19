"""
Cleanup script: strips \r\r\n back to \n in all .trepan/*.md pillar files.
Run once after the server fix to repair already-corrupted files.
"""
import os
import glob

def fix_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # \r\r\n → \n  (the doubled-CRLF artifact)
    # \r\n   → \n  (standard Windows CRLF)
    # \r     → \n  (old Mac CR)
    fixed = content.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")

    if fixed == content:
        print(f"  [OK]      {path} — no changes needed")
        return

    # Write back without Python adding \r\n again (newline="" disables translation)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(fixed)
    print(f"  [FIXED]   {path}")

projects = [
    r"c:\Users\ethan\Documents\Projects\Trepan_Test_Zone",
    r"c:\Users\ethan\Documents\Projects\Trepan",
]

for proj in projects:
    trepan_dir = os.path.join(proj, ".trepan")
    if not os.path.isdir(trepan_dir):
        print(f"  [SKIP]  No .trepan dir in {proj}")
        continue
    for md_file in glob.glob(os.path.join(trepan_dir, "*.md")):
        fix_file(md_file)
    # Also fix vault copies
    vault_dir = os.path.join(trepan_dir, "trepan_vault")
    if os.path.isdir(vault_dir):
        for md_file in glob.glob(os.path.join(vault_dir, "*.md")):
            fix_file(md_file)

print("\nDone.")
