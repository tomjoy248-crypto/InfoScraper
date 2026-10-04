"""构建 InfoScraper 安装包。"""

import os
import shutil
import subprocess
import sys

FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer", "files")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setup_output")


def main():
    source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer_source.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_setup_temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_main = os.path.join(temp_dir, "setup_main.py")
    with open(temp_main, "w", encoding="utf-8") as f:
        f.write(source)
    for name in ("InfoScraper.exe", "README.md", "USER_GUIDE.md"):
        shutil.copy2(os.path.join(FILES_DIR, name), os.path.join(temp_dir, name))

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
            "--add-data", f"{os.path.join(temp_dir, 'InfoScraper.exe')};.",
            "--add-data", f"{os.path.join(temp_dir, 'README.md')};.",
            "--add-data", f"{os.path.join(temp_dir, 'USER_GUIDE.md')};.",
            temp_main,
        ],
        check=True,
    )

    # 清理临时目录
    shutil.rmtree(temp_dir, ignore_errors=True)
    print(f"安装包已生成: {os.path.join(OUTPUT_DIR, 'InfoScraper-Setup.exe')}")


if __name__ == "__main__":
    main()
