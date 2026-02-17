import os
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent / "docs"

def get_content(filename, folder=FOLDER):
    print(f"get_content of {filename}")
    content = ""
    file_path = os.path.join(folder, filename)
    print(f"get_content file_path = {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()
    return content