import zipfile
import os
def extract(zip_path, dest_dir):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            # VULNERABLE: Zip Slip traversal without sanitizing the extract path
            extracted_path = os.path.join(dest_dir, member)
            zip_ref.extract(member, dest_dir)
