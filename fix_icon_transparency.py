#!/usr/bin/env python3
"""
Fix Extension Branding Assets
Remove white/checkerboard background from icons and make them transparent.
"""

import os
from PIL import Image

def make_transparent(img_path):
    """
    Remove white/light backgrounds from PNG images and make them transparent.
    
    Args:
        img_path: Path to the PNG image file
    """
    if not os.path.exists(img_path):
        print(f"❌ File {img_path} not found.")
        return False
    
    print(f"🔄 Processing {img_path}...")
    
    # Open and convert to RGBA
    img = Image.open(img_path).convert("RGBA")
    datas = img.getdata()
    
    new_data = []
    pixels_changed = 0
    
    for item in datas:
        # Check for white or light-grey pixels (checkerboard)
        # Threshold: if R, G, and B are all > 200, make it transparent
        if item[0] > 200 and item[1] > 200 and item[2] > 200:
            new_data.append((255, 255, 255, 0))  # Fully transparent
            pixels_changed += 1
        else:
            new_data.append(item)
    
    # Apply the new data
    img.putdata(new_data)
    
    # Save back to the same path
    img.save(img_path, "PNG")
    
    print(f"✅ Successfully cleaned {img_path}")
    print(f"   Changed {pixels_changed:,} pixels to transparent")
    return True

def main():
    """Main execution function"""
    print("🛡️  SemantGuard Icon Transparency Fixer")
    print("=" * 50)
    
    # Target both icons
    icons = [
        "extension/icons/icon128.png",
        "extension/icons/icon512.png"
    ]
    
    success_count = 0
    for icon_path in icons:
        if make_transparent(icon_path):
            success_count += 1
        print()
    
    print("=" * 50)
    print(f"✨ Complete! Fixed {success_count}/{len(icons)} icons")
    
    # Verify package.json still points correctly
    package_json_path = "extension/package.json"
    if os.path.exists(package_json_path):
        with open(package_json_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if '"icon": "icons/icon128.png"' in content:
                print("✅ package.json icon reference verified")
            else:
                print("⚠️  Warning: package.json icon reference may need updating")
    
    print("\n🎉 All done! Your icons now have transparent backgrounds.")

if __name__ == "__main__":
    main()
