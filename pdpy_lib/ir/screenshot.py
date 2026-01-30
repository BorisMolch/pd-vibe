"""
Screenshot Pure Data patches using macOS automation.

Opens patches in Pd, captures screenshots, and closes them.
Requires Pure Data to be installed.
"""

import subprocess
import time
import os
from pathlib import Path
from typing import Optional


def find_pd_app() -> Optional[str]:
    """Find Pure Data application on macOS."""
    candidates = [
        "/Applications/Pd-0.55-2.app",
        "/Applications/Pd-0.55-1.app",
        "/Applications/Pd-0.55-0.app",
        "/Applications/Pd-0.54-1.app",
        "/Applications/Pd-0.54-0.app",
        "/Applications/Pd.app",
        "/Applications/Purr Data.app",
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    # Try to find any Pd app
    result = subprocess.run(
        ["mdfind", "kMDItemCFBundleIdentifier == 'org.puredata.pd'"],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        return result.stdout.strip().split('\n')[0]

    return None


def screenshot_patch(
    pd_path: str,
    output_path: Optional[str] = None,
    wait_time: float = 1.5,
    pd_app: Optional[str] = None,
) -> Optional[str]:
    """
    Take a screenshot of a Pure Data patch.

    Args:
        pd_path: Path to the .pd file
        output_path: Where to save the screenshot (default: same dir as pd file)
        wait_time: Seconds to wait for Pd to open the patch
        pd_app: Path to Pd application (auto-detected if not provided)

    Returns:
        Path to the screenshot, or None if failed
    """
    pd_path = Path(pd_path).resolve()

    if not pd_path.exists():
        raise FileNotFoundError(f"Patch not found: {pd_path}")

    if output_path is None:
        output_path = pd_path.parent / f"{pd_path.name}.png"
    else:
        output_path = Path(output_path)

    # Find Pd
    if pd_app is None:
        pd_app = find_pd_app()
        if pd_app is None:
            raise RuntimeError("Could not find Pure Data application")

    # AppleScript to open patch, screenshot, and close
    applescript = f'''
    tell application "{pd_app}"
        activate
        open POSIX file "{pd_path}"
    end tell

    delay {wait_time}

    -- Find the patch window (should be frontmost)
    tell application "System Events"
        tell process "Pd"
            set frontWindow to window 1
            set windowBounds to position of frontWindow & size of frontWindow
        end tell
    end tell

    -- Calculate screenshot bounds
    set x1 to item 1 of windowBounds
    set y1 to item 2 of windowBounds
    set w to item 3 of windowBounds
    set h to item 4 of windowBounds

    -- Take screenshot using screencapture
    do shell script "screencapture -R" & x1 & "," & y1 & "," & w & "," & h & " \\"{output_path}\\""

    -- Close the patch window
    tell application "{pd_app}"
        close window 1
    end tell

    return "{output_path}"
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            print(f"AppleScript error: {result.stderr}")
            return None

        if output_path.exists():
            return str(output_path)
        else:
            return None

    except subprocess.TimeoutExpired:
        print("Screenshot timed out")
        return None
    except Exception as e:
        print(f"Screenshot error: {e}")
        return None


def screenshot_patch_simple(
    pd_path: str,
    output_path: Optional[str] = None,
    wait_time: float = 2.0,
) -> Optional[str]:
    """
    Simpler screenshot approach using screencapture with window selection.

    This opens the patch and uses screencapture's window capture mode.
    """
    pd_path = Path(pd_path).resolve()

    if not pd_path.exists():
        raise FileNotFoundError(f"Patch not found: {pd_path}")

    if output_path is None:
        output_path = pd_path.parent / f"{pd_path.name}.png"
    else:
        output_path = Path(output_path)

    pd_app = find_pd_app()
    if pd_app is None:
        raise RuntimeError("Could not find Pure Data application")

    # Open the patch
    subprocess.run(["open", "-a", pd_app, str(pd_path)])

    # Wait for window to open
    time.sleep(wait_time)

    # Use screencapture to capture the frontmost window
    # -l requires window ID, -w is interactive - let's use a different approach

    # Get the window ID using AppleScript
    get_window_script = '''
    tell application "System Events"
        tell process "Pd"
            set frontWindow to window 1
            return id of frontWindow
        end tell
    end tell
    '''

    try:
        # Take screenshot of frontmost window
        result = subprocess.run(
            ["screencapture", "-l", "0", "-o", str(output_path)],
            capture_output=True, text=True, timeout=10
        )

        # Close the window
        close_script = f'''
        tell application "{pd_app}"
            close window 1
        end tell
        '''
        subprocess.run(["osascript", "-e", close_script], capture_output=True)

        if output_path.exists():
            return str(output_path)
        return None

    except Exception as e:
        print(f"Screenshot error: {e}")
        return None


def screenshot_with_screencapture(
    pd_path: str,
    output_path: Optional[str] = None,
    wait_time: float = 1.5,
) -> Optional[str]:
    """
    Screenshot using screencapture -w (window mode) after opening patch.

    Note: This requires user interaction to click on the window.
    For fully automated screenshots, use screenshot_patch().
    """
    pd_path = Path(pd_path).resolve()

    if output_path is None:
        output_path = pd_path.parent / f"{pd_path.name}.png"

    pd_app = find_pd_app()
    if pd_app is None:
        raise RuntimeError("Could not find Pure Data application")

    # Open the patch
    subprocess.run(["open", "-a", pd_app, str(pd_path)])
    time.sleep(wait_time)

    print(f"Click on the Pd patch window to capture it...")

    # Interactive window capture
    subprocess.run(["screencapture", "-w", "-o", str(output_path)])

    if Path(output_path).exists():
        return str(output_path)
    return None


def screenshot_patch_v2(
    pd_path: str,
    output_path: Optional[str] = None,
    wait_time: float = 2.0,
) -> Optional[str]:
    """
    Screenshot using window name matching.

    Opens patch, finds window by name, screenshots it.
    """
    pd_path = Path(pd_path).resolve()

    if not pd_path.exists():
        raise FileNotFoundError(f"Patch not found: {pd_path}")

    if output_path is None:
        output_path = pd_path.parent / f"{pd_path.name}.png"
    else:
        output_path = Path(output_path)

    pd_app = find_pd_app()
    if pd_app is None:
        raise RuntimeError("Could not find Pure Data application")

    patch_name = pd_path.stem

    # Open the patch
    subprocess.run(["open", "-a", pd_app, str(pd_path)])
    time.sleep(wait_time)

    # Get window ID by name using CGWindowListCopyWindowInfo
    applescript = f'''
    tell application "System Events"
        tell process "Pd"
            set allWindows to every window
            repeat with w in allWindows
                if name of w contains "{patch_name}" then
                    -- Get window bounds
                    set pos to position of w
                    set sz to size of w
                    set x to item 1 of pos
                    set y to item 2 of pos
                    set width to item 1 of sz
                    set height to item 2 of sz

                    -- Take screenshot
                    do shell script "screencapture -R" & x & "," & y & "," & width & "," & height & " \\"{output_path}\\""

                    return "ok"
                end if
            end repeat
        end tell
    end tell
    return "not found"
    '''

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True, text=True, timeout=15
        )

        # Close the patch window using keyboard shortcut
        close_script = '''
        tell application "System Events"
            tell process "Pd"
                keystroke "w" using command down
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", close_script], capture_output=True, timeout=5)

        if "ok" in result.stdout:
            if output_path.exists():
                return str(output_path)

        print(f"Result: {result.stdout} {result.stderr}")
        return None

    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python screenshot.py <patch.pd> [output.png]")
        sys.exit(1)

    pd_file = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None

    result = screenshot_patch_v2(pd_file, output)
    if result:
        print(f"Screenshot saved to: {result}")
    else:
        print("Screenshot failed")
        sys.exit(1)
