"""构建 InfoScraper 安装包。"""

import base64
import os
import shutil
import subprocess
import sys

FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer", "files")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_output")


def encode_file(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def main():
    source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer_source.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    replacements = {
        "__INFO_SCRAPER_EXE__": encode_file(os.path.join(FILES_DIR, "InfoScraper.exe")),
        "__README_MD__": encode_file(os.path.join(FILES_DIR, "README.md")),
        "__USER_GUIDE_MD__": encode_file(os.path.join(FILES_DIR, "USER_GUIDE.md")),
    }

    for placeholder, data in replacements.items():
        source = source.replace(f'"{placeholder}"', f'"{data}"')

    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_setup_temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_main = os.path.join(temp_dir, "setup_main.py")
    with open(temp_main, "w", encoding="utf-8") as f:
        f.write(source)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--name", "InfoScraper-Setup",
            "--distpath", OUTPUT_DIR,
            "--workpath", os.path.join(temp_dir, "build"),
            "--specpath", temp_dir,
            temp_main,
        ],
        check=True,
    )

    # 清理临时目录
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"安装包已生成: {os.path.join(OUTPUT_DIR, 'InfoScraper-Setup.exe')}")


if __name__ == "__main__":
    main()
