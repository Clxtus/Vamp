import os
from PIL import Image

jpg_path = r"C:\Users\sara's pc\Desktop\Suleman\Studio\Vamp\vamp-vscode\vamp-icon.png"
ico_path = r"C:\Users\sara's pc\Desktop\Suleman\Studio\Vamp\vamp-icon.ico"

if os.path.exists(jpg_path):
    img = Image.open(jpg_path)
    img.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    print("Successfully created valid vamp-icon.ico!")
else:
    print(f"Could not find {jpg_path}")