"""简易安装程序：解压内置文件到用户选择目录，并创建快捷方式。"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict

# 安装文件内容（base64）会在构建时被替换
_FILES = ("InfoScraper.exe", "README.md", "USER_GUIDE.md")


def _create_shortcut(target: str, shortcut_path: str, description: str = "InfoScraper"):
    """创建 Windows 快捷方式。"""
    try:
        import winshell
        from win32com.client import Dispatch
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = target
        shortcut.WorkingDirectory = os.path.dirname(target)
        shortcut.Description = description
        shortcut.save()
    except Exception:
        # 若未安装 winshell/pywin32，则跳过快捷方式创建
        pass


def main():
    root = tk.Tk()
    root.withdraw()

    default_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "InfoScraper")
    install_dir = filedialog.askdirectory(initialdir=os.path.dirname(default_dir), title="选择 InfoScraper 安装目录")
    if not install_dir:
        sys.exit(0)

    install_dir = os.path.join(install_dir, "InfoScraper")
    os.makedirs(install_dir, exist_ok=True)

    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for filename in _FILES:
        with open(os.path.join(bundle_dir, filename), "rb") as source:
            data = source.read()
        path = os.path.join(install_dir, filename)
        with open(path, "wb") as f:
            f.write(data)

    # 创建开始菜单快捷方式
    try:
        start_menu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "InfoScraper")
        os.makedirs(start_menu, exist_ok=True)
        _create_shortcut(
            os.path.join(install_dir, "InfoScraper.exe"),
            os.path.join(start_menu, "InfoScraper.lnk"),
        )
    except Exception:
        pass

    # 询问是否创建桌面快捷方式
    if messagebox.askyesno("安装完成", "是否在桌面创建快捷方式？"):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        _create_shortcut(
            os.path.join(install_dir, "InfoScraper.exe"),
            os.path.join(desktop, "InfoScraper.lnk"),
        )

    messagebox.showinfo("安装完成", f"InfoScraper 已安装到:\n{install_dir}")


if __name__ == "__main__":
    main()
