"""
Utility for launching Chrome on the same monitor as the active VS Code window.
Windows only. Requires: pywin32, screeninfo.
"""

import os
import subprocess
import tempfile
import time

import win32gui
import win32con
from screeninfo import get_monitors


def _find_vscode_hwnd(project_hint=None):
    """
    Return the window handle of a VS Code window.

    Search order:
      1. VS Code window whose title contains project_hint (if provided)
      2. The foreground window, if it's VS Code
      3. Any visible VS Code window
    """
    all_vscode = []

    def _enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "Visual Studio Code" in title:
                all_vscode.append((hwnd, title))

    win32gui.EnumWindows(_enum_cb, None)

    # 1. Match on project name
    if project_hint:
        for hwnd, title in all_vscode:
            if project_hint.lower() in title.lower():
                return hwnd

    # 2. Foreground window
    fg = win32gui.GetForegroundWindow()
    for hwnd, _ in all_vscode:
        if hwnd == fg:
            return hwnd

    # 3. Any VS Code window
    return all_vscode[0][0] if all_vscode else None


def _monitor_for_point(x, y):
    """Return the monitor that contains the point (x, y), or the primary monitor."""
    for m in get_monitors():
        if m.x <= x < m.x + m.width and m.y <= y < m.y + m.height:
            return m
    # Fall back to primary
    for m in get_monitors():
        if m.is_primary:
            return m
    return get_monitors()[0]


def _find_chrome():
    """Auto-detect Chrome install path from common Windows locations."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def launch_chrome_on_vscode_monitor(url: str, chrome_path: str = None):
    """
    Launch Chrome on the same monitor as the currently active VS Code window.

    Args:
        url: The URL to open.
        chrome_path: Path to chrome.exe. Auto-detected if not provided.

    Returns:
        The subprocess.Popen object for the launched Chrome process.

    Raises:
        FileNotFoundError: If Chrome cannot be found.
    """
    chrome = chrome_path or _find_chrome()
    if not chrome or not os.path.isfile(chrome):
        raise FileNotFoundError(
            f"Chrome not found at '{chrome}'. Pass chrome_path explicitly."
        )

    # Auto-detect project name from cwd for multi-window matching
    project_name = os.path.basename(os.getcwd())
    hwnd = _find_vscode_hwnd(project_hint=project_name)
    if hwnd:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        cx, cy = (left + right) // 2, (top + bottom) // 2
        monitor = _monitor_for_point(cx, cy)
    else:
        print("VS Code window not found — falling back to primary monitor.")
        monitor = _monitor_for_point(0, 0)

    # Use a temp user-data-dir so Chrome doesn't merge into an existing session
    tmp_profile = tempfile.mkdtemp(prefix="chrome_monitor_")
    cmd = [
        chrome,
        f"--user-data-dir={tmp_profile}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    # Snapshot existing Chrome windows before launch
    existing = set()

    def _snap(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and "Chrome" in win32gui.GetWindowText(hwnd):
            existing.add(hwnd)

    win32gui.EnumWindows(_snap, None)

    proc = subprocess.Popen(cmd)

    # Wait for the NEW Chrome window, then move it to the target monitor
    deadline = time.time() + 5
    while time.time() < deadline:
        time.sleep(0.3)
        new_hwnd = None

        def _find_new(hwnd, _):
            nonlocal new_hwnd
            if (win32gui.IsWindowVisible(hwnd)
                    and "Chrome" in win32gui.GetWindowText(hwnd)
                    and hwnd not in existing):
                new_hwnd = hwnd

        win32gui.EnumWindows(_find_new, None)

        if new_hwnd:
            # Move immediately, then again after Chrome finishes its own positioning
            for _ in range(3):
                win32gui.SetWindowPos(
                    new_hwnd, None,
                    monitor.x, monitor.y, monitor.width, monitor.height,
                    win32con.SWP_NOZORDER,
                )
                time.sleep(0.5)
            break

    return proc


def get_vscode_monitor():
    """
    Return the monitor where the current project's VS Code window lives.
    Falls back to the primary monitor if VS Code isn't found.
    """
    project_name = os.path.basename(os.getcwd())
    hwnd = _find_vscode_hwnd(project_hint=project_name)
    if hwnd:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        cx, cy = (left + right) // 2, (top + bottom) // 2
        return _monitor_for_point(cx, cy)
    return _monitor_for_point(0, 0)


def get_chrome_window_args():
    """
    Return a list of Chrome CLI args to position the window on the VS Code monitor.
    Use with nodriver: browser_args.extend(get_chrome_window_args())
    """
    m = get_vscode_monitor()
    return [f"--window-position={m.x},{m.y}", f"--window-size={m.width},{m.height}"]


def move_chrome_to_vscode_monitor():
    """
    Find all visible Chrome windows and move them to the VS Code monitor.
    Call after nodriver launches Chrome (with a short delay for the window to appear).
    """
    m = get_vscode_monitor()
    moved = False

    def _cb(hwnd, _):
        nonlocal moved
        if win32gui.IsWindowVisible(hwnd) and "Chrome" in win32gui.GetWindowText(hwnd):
            rect = win32gui.GetWindowRect(hwnd)
            # Skip offscreen/minimized windows
            if rect[0] <= -30000:
                return
            win32gui.SetWindowPos(
                hwnd, None, m.x, m.y, m.width, m.height,
                win32con.SWP_NOZORDER,
            )
            moved = True

    # Move repeatedly to beat Chrome's own repositioning
    for _ in range(3):
        win32gui.EnumWindows(_cb, None)
        time.sleep(0.5)

    return moved


if __name__ == "__main__":
    launch_chrome_on_vscode_monitor("https://example.com")
