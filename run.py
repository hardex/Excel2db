"""Standalone entry point for Excel2DB."""
import os
import sys
import webbrowser
from pathlib import Path

# When bundled by PyInstaller, files are extracted to a temp dir.
# We need to set the working directory so relative paths work.
if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle
    bundle_dir = sys._MEIPASS
    # Use user's home directory for data folders
    data_dir = Path.home() / "Excel2DB"
    data_dir.mkdir(exist_ok=True)
    for folder in ("mappings", "outputs", "logs", "uploads"):
        (data_dir / folder).mkdir(exist_ok=True)
    os.chdir(data_dir)
    # Copy bundled templates/static to data dir if not present
    import shutil
    bundled_app = Path(bundle_dir) / "app"
    local_app = data_dir / "app"
    if not local_app.exists():
        shutil.copytree(bundled_app, local_app)
    else:
        # Always update templates and static from bundle
        for sub in ("templates", "static"):
            src = bundled_app / sub
            dst = local_app / sub
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
else:
    # Running from source
    os.chdir(Path(__file__).parent)

import uvicorn

HOST = "127.0.0.1"
PORT = 8000


def main():
    print(f"Starting Excel2DB at http://{HOST}:{PORT}")
    webbrowser.open(f"http://{HOST}:{PORT}")
    uvicorn.run("app.main:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
