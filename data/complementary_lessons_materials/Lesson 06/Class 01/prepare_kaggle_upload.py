import os
import zipfile
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def main():
    print("🚀 Preparing Kaggle Dataset Payload...")
    
    # Define paths robustly using __file__ so it doesn't matter where the student runs it from
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    env_source = os.path.join(project_root, '.env')
    raw_zip_path = os.path.join(script_dir, 'raw_bootcampgis_kaggle_dataset.zip')
    output_zip_path = os.path.join(script_dir, 'bootcampgis_kaggle_dataset.zip')

    # 1. Check if .env exists
    if not os.path.exists(env_source):
        print(f"❌ ERROR: Could not find .env file at {env_source}")
        print("Please make sure you are running this script from the notebooks/kaggle_deploy/ folder!")
        return

    # 2. Check if the raw dataset zip exists
    if not os.path.exists(raw_zip_path):
        print(f"❌ ERROR: Could not find {raw_zip_path}")
        print("Please make sure the raw zip file is in the same folder as this script.")
        return

    print(f"📦 Generating final dataset: {output_zip_path}...")
    
    # 3. Create the new zip file
    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as out_zip:
        # A. Copy all contents from the raw zip into the new zip
        print(f"  [+] Reading contents from {raw_zip_path}...")
        with zipfile.ZipFile(raw_zip_path, 'r') as in_zip:
            for item in in_zip.infolist():
                # Read the file content from the raw zip and write it to the new zip
                content = in_zip.read(item.filename)
                out_zip.writestr(item, content)
                print(f"  [+] Merged {item.filename}")
        
        # B. Add the .env file to the root of the new zip
        out_zip.write(env_source, arcname='.env')
        print("  [+] Merged .env (Secure Local File)")

    print(f"\n✅ Success! Your payload is ready: {os.path.abspath(output_zip_path)}")
    print("👉 Next Step: Upload this new .zip file to Kaggle as a Private Dataset!")

if __name__ == '__main__':
    main()
