from __future__ import annotations

import os
import platform
import subprocess


def _pick_directory_macos(title: str) -> str | None:
    script = f'''
    set chosenFolder to choose folder with prompt "{title}"
    POSIX path of chosenFolder
    '''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    return path or None


def _pick_directory_windows(title: str) -> str | None:
    script = rf"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "{title}"
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
  Write-Output $dialog.SelectedPath
}}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    return path or None


def _pick_directory_tk(title: str) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(title=title)
    root.destroy()
    return path or None


def pick_directory(title: str) -> str | None:
    system = platform.system().lower()
    if system == "darwin":
        # Avoid tkinter fallback on macOS: this endpoint runs inside FastAPI's
        # worker thread, and initializing Tk from a non-main thread can abort
        # the process after the native dialog is cancelled.
        return _pick_directory_macos(title)
    if system == "windows":
        return _pick_directory_windows(title)
    return _pick_directory_tk(title) or os.getcwd()
