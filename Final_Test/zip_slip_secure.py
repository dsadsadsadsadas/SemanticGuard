import zipfile
import os
def extract(zip_path, dest_dir):
    dest_dir = os.path.abspath(dest_dir)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.namelist():
            # SAFE: Checking realpath constraints to prevent Zip Slip
            target_path = os.path.abspath(os.path.join(dest_dir, member))
            if not target_path.startswith(dest_dir + os.sep):
                raise Exception("Zip Slip detected!")
            zip_ref.extract(member, dest_dir)
