"""
ScreenRotator Auto  —  © 2026  L. Malakar
https://github.com/L-Malakar/

Revision notes (this build):
  • Hotkey defaults changed to Ctrl+Alt+[Arrow]
  • Orientation mapping verified: up=0° Landscape, right=90° Portrait,
    down=180° Landscape Flipped, left=270° Portrait Flipped
  • Settings now use DEFERRED save — changes only take effect on "Save Changes"
  • "Close without saving" triggers an unsaved-changes warning dialog
  • "How to Use" blank/reopen bug fixed — full frame destruction + rebuild
  • Comprehensive rendering review — all Toplevel windows rebuilt cleanly
  • Thread-safe hotkey registration via _hotkey_mutex (only on Save)
  • logo.ico applied to every window via iconbitmap + WM_SETICON
"""

import rotatescreen
import keyboard
import os, sys, subprocess, ctypes, json, copy, webbrowser
import winshell
from win32com.client import Dispatch
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageTk
import tkinter as tk
import threading
import time

# ─────────────────────────────────────────────────────────────────────────────
# PyInstaller path helper
# ─────────────────────────────────────────────────────────────────────────────
def resource_path(relative_path):
    """Absolute path that works both in dev and inside a PyInstaller bundle."""
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.abspath(".")
    return os.path.join(base, relative_path)


# ─────────────────────────────────────────────────────────────────────────────
# Paths & constants
# ─────────────────────────────────────────────────────────────────────────────
TASK_NAME    = "ScreenRotatorAuto"
APPDATA_PATH = os.getenv("APPDATA", os.path.expanduser("~"))
CONFIG_PATH  = os.path.join(APPDATA_PATH, "rotator_settings.json")

LOGO_PATH          = resource_path("logo.png")
SHORTCUT_LOGO_PATH = resource_path("logo2.png")
ICO_PATH           = resource_path("logo.ico")

APP_AUTHOR     = "L. Malakar"
APP_YEAR       = "2026"
APP_GITHUB_URL = "https://github.com/L-Malakar/"
FOOTER_TEXT    = f"\u00a9 {APP_YEAR} | Open Source Project by {APP_AUTHOR}"

BG_COLOR        = "#212121"
HEADER_COLOR    = "#1a1a1a"
FG_COLOR        = "#FFFFFF"
ACCENT_COLOR    = "#4CAF50"
BTN_BG          = "#333333"
LIVE_COLOR      = "#00FF00"
WARN_COLOR      = "#FFA500"
CLOSE_BTN_HOVER = "#e81123"
LINK_COLOR      = "#4da6ff"

# ─────────────────────────────────────────────────────────────────────────────
# Orientation mapping
# ─────────────────────────────────────────────────────────────────────────────
#   key    display name          degrees   rotatescreen method
#   "up"   Landscape             0°        set_landscape()
#   "right" Portrait             90°       set_portrait_flipped()   ← Win uses
#   "down"  Landscape Flipped    180°      set_landscape_flipped()        CW
#   "left"  Portrait Flipped     270°      set_portrait()           ← rotation
#
# Windows DMDO rotation values:
#   DMDO_DEFAULT (0)   = Landscape
#   DMDO_90      (1)   = Portrait          (rotated 90° CW from landscape)
#   DMDO_180     (2)   = Landscape Flipped
#   DMDO_270     (3)   = Portrait Flipped  (rotated 270° CW from landscape)
#
# rotatescreen maps:
#   set_landscape()         → DMDO_DEFAULT (0°)
#   set_portrait()          → DMDO_270     (270°)   ← left key
#   set_landscape_flipped() → DMDO_180     (180°)   ← down key
#   set_portrait_flipped()  → DMDO_90      (90°)    ← right key
# ─────────────────────────────────────────────────────────────────────────────
DIRECTION_DISPLAY = {
    "up":    "Landscape (0\u00b0)",
    "right": "Portrait (90\u00b0)",
    "down":  "Landscape Flipped (180\u00b0)",
    "left":  "Portrait Flipped (270\u00b0)",
}


# ─────────────────────────────────────────────────────────────────────────────
# Win32 icon helper — works even on overrideredirect windows
# ─────────────────────────────────────────────────────────────────────────────
def _win32_set_icon(hwnd: int) -> None:
    """Push logo.ico into a window's ICON_SMALL and ICON_BIG slots."""
    if not os.path.exists(ICO_PATH):
        return
    try:
        WM_SETICON      = 0x0080
        IMAGE_ICON      = 1
        LR_LOADFROMFILE = 0x0010
        u32 = ctypes.windll.user32
        for size, slot in ((16, 0), (32, 1)):
            hicon = u32.LoadImageW(None, ICO_PATH, IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if hicon:
                u32.SendMessageW(hwnd, WM_SETICON, slot, hicon)
    except Exception:
        pass


def set_icon_on_window(win: tk.BaseWidget) -> None:
    """
    Apply logo.ico to a Tk/Toplevel window at every level:
      1. iconbitmap()  — standard title-bar icon
      2. WM_SETICON    — taskbar button + Alt+Tab thumbnail
    Safe to call before or after overrideredirect().
    """
    if os.path.exists(ICO_PATH):
        try:
            win.iconbitmap(ICO_PATH)
        except Exception:
            pass
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        _win32_set_icon(hwnd)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Main application class
# ─────────────────────────────────────────────────────────────────────────────
class RotatorApp:

    def __init__(self):
        # Verify display access
        try:
            self.display = rotatescreen.get_primary_display()
        except Exception as exc:
            # Tk may not exist yet — use ctypes MessageBox as last resort
            ctypes.windll.user32.MessageBoxW(
                0, f"Could not find display:\n{exc}", "ScreenRotator — Error", 0x10)
            sys.exit(1)

        # Committed (live) hotkeys loaded from disk
        self.hotkeys = self.load_config()
        self.icon    = None

        # Per-window open/close guards
        self._settings_lock     = threading.Lock()
        self._instructions_lock = threading.Lock()

        # Serialises keyboard.unhook_all / add_hotkey / read_hotkey calls
        self._hotkey_mutex = threading.Lock()

        # Single hidden Tk root — ALL Toplevel windows are children of this
        self._tk_root  = None
        self._tk_ready = threading.Event()
        threading.Thread(target=self._run_tk_root, daemon=True).start()
        self._tk_ready.wait()   # block until root.mainloop() is spinning

    # ── Tk root ───────────────────────────────────────────────────────────────

    def _run_tk_root(self) -> None:
        """Single persistent hidden root; owns the Tk event loop."""
        root = tk.Tk()
        root.withdraw()
        root.title("ScreenRotator")
        set_icon_on_window(root)
        self._tk_root  = root
        self._tk_ready.set()
        root.mainloop()

    def _make_toplevel(self) -> tk.Toplevel:
        """Construct a fresh, hidden, icon-bearing Toplevel on the shared root."""
        win = tk.Toplevel(self._tk_root)
        win.withdraw()
        win.configure(bg=BG_COLOR)
        set_icon_on_window(win)
        return win

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self) -> dict:
        """Return saved hotkeys or fall back to Ctrl+Alt+[Arrow] defaults."""
        defaults = {
            "up":    "ctrl+alt+up",
            "right": "ctrl+alt+right",
            "down":  "ctrl+alt+down",
            "left":  "ctrl+alt+left",
        }
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as fh:
                    loaded = json.load(fh)
                # Validate all four keys are present
                if all(k in loaded for k in defaults):
                    return loaded
            except Exception:
                pass
        return defaults

    def _commit_and_save(self, pending: dict) -> None:
        """
        Deferred save — called only when the user clicks 'Save Changes'.
        Writes pending dict to disk, commits it as the live hotkey set,
        then re-registers hotkeys thread-safely.
        """
        self.hotkeys = copy.deepcopy(pending)
        try:
            with open(CONFIG_PATH, "w") as fh:
                json.dump(self.hotkeys, fh, indent=2)
        except Exception:
            pass
        self.start_hotkeys()
        self.show_toast("Settings Saved Successfully")

    # ── Hotkey registration ───────────────────────────────────────────────────

    def start_hotkeys(self) -> None:
        """
        Thread-safe (re-)registration of all four global hotkeys.
        Uses _hotkey_mutex so no parallel read_hotkey / unhook_all can race.

        Orientation map (verified against Windows DMDO values):
          up    → set_landscape()         0°   Landscape
          right → set_portrait_flipped()  90°  Portrait
          down  → set_landscape_flipped() 180° Landscape Flipped
          left  → set_portrait()          270° Portrait Flipped
        """
        def _register():
            with self._hotkey_mutex:
                try:
                    keyboard.unhook_all()
                except Exception:
                    pass
                try:
                    keyboard.add_hotkey(
                        self.hotkeys["up"],
                        self.display.set_landscape,
                        suppress=True)
                    keyboard.add_hotkey(
                        self.hotkeys["right"],
                        self.display.set_portrait_flipped,   # 90° CW
                        suppress=True)
                    keyboard.add_hotkey(
                        self.hotkeys["down"],
                        self.display.set_landscape_flipped,  # 180°
                        suppress=True)
                    keyboard.add_hotkey(
                        self.hotkeys["left"],
                        self.display.set_portrait,           # 270° CW
                        suppress=True)
                except Exception:
                    pass

        threading.Thread(target=_register, daemon=True).start()

    # ── Notifications ─────────────────────────────────────────────────────────

    def show_toast(self, message: str) -> None:
        """Bottom-right toast that auto-dismisses after 2 s."""
        def _create():
            toast = self._make_toplevel()
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.configure(bg=ACCENT_COLOR)
            w, h = 280, 52
            sw   = toast.winfo_screenwidth()
            sh   = toast.winfo_screenheight()
            toast.geometry(f"{w}x{h}+{sw - w - 20}+{sh - h - 60}")
            tk.Label(toast, text=message, fg=FG_COLOR, bg=ACCENT_COLOR,
                     font=("Arial", 10, "bold")).pack(expand=True)
            toast.deiconify()
            toast.after(2000, toast.destroy)
        self._tk_root.after(0, _create)

    def show_status_notification(self, parent: tk.Widget,
                                  message: str, color: str = ACCENT_COLOR) -> None:
        """
        Thin non-blocking inline banner anchored just below *parent*.
        Replaces blocking MessageBox for Add/Delete feedback.
        """
        def _create():
            try:
                parent.update_idletasks()
                px = parent.winfo_x()
                py = parent.winfo_y() + parent.winfo_height() + 4
                pw = max(parent.winfo_width(), 200)
            except Exception:
                return
            banner = tk.Toplevel(parent)
            banner.overrideredirect(True)
            banner.attributes("-topmost", True)
            banner.configure(bg=color)
            set_icon_on_window(banner)
            banner.geometry(f"{pw}x34+{px}+{py}")
            tk.Label(banner, text=message, fg=FG_COLOR, bg=color,
                     font=("Arial", 9, "bold")).pack(expand=True)
            banner.deiconify()
            banner.after(2000, banner.destroy)
        self._tk_root.after(0, _create)

    # ── Window scaffold ───────────────────────────────────────────────────────

    def center_window(self, win: tk.BaseWidget, w: int, h: int) -> None:
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def apply_custom_title_bar(self, win: tk.BaseWidget,
                                title_text: str,
                                logo_img: str | None = None,
                                on_close_cb=None) -> None:
        """
        Attach a dark-mode custom title bar to *win*.
        *on_close_cb* — called when ✕ is clicked (defaults to win.destroy).
        Icon is applied via WM_SETICON after overrideredirect so it persists
        in Alt+Tab even though the standard chrome is hidden.
        """
        win.overrideredirect(True)
        # Re-apply icon AFTER overrideredirect because the HWND changes on some
        # Windows versions when decoration is removed.
        self._tk_root.after(50, lambda: set_icon_on_window(win))

        bar = tk.Frame(win, bg=HEADER_COLOR, height=32, highlightthickness=0)
        bar.pack(fill="x", side="top")

        # Logo thumbnail
        if logo_img and os.path.exists(logo_img):
            try:
                img    = Image.open(logo_img).resize((20, 20))
                render = ImageTk.PhotoImage(img, master=win)
                ico_lbl = tk.Label(bar, image=render, bg=HEADER_COLOR)
                ico_lbl.image = render          # prevent GC
                ico_lbl.pack(side="left", padx=10)
            except Exception:
                pass

        tk.Label(bar, text=title_text, fg="#888888",
                 bg=HEADER_COLOR, font=("Arial", 9)).pack(side="left")

        # Close button
        closer = on_close_cb if on_close_cb else win.destroy
        close_btn = tk.Label(bar, text="\u2715", fg=FG_COLOR,
                             bg=HEADER_COLOR, width=4, font=("Arial", 10))
        close_btn.pack(side="right", fill="y")
        close_btn.bind("<Button-1>", lambda _e: closer())
        close_btn.bind("<Enter>",    lambda _e: close_btn.config(bg=CLOSE_BTN_HOVER))
        close_btn.bind("<Leave>",    lambda _e: close_btn.config(bg=HEADER_COLOR))

        # Drag-to-move
        def _start(e): win._drag_x, win._drag_y = e.x, e.y
        def _stop(_e): win._drag_x = win._drag_y = None
        def _move(e):
            dx = e.x - win._drag_x
            dy = e.y - win._drag_y
            win.geometry(f"+{win.winfo_x() + dx}+{win.winfo_y() + dy}")

        bar.bind("<Button-1>",        _start)
        bar.bind("<ButtonRelease-1>", _stop)
        bar.bind("<B1-Motion>",       _move)

    # ── Exit dialog ───────────────────────────────────────────────────────────

    def confirm_exit(self) -> None:
        def _create():
            dlg = self._make_toplevel()
            self.apply_custom_title_bar(dlg, "Exit")
            self.center_window(dlg, 360, 185)
            dlg.attributes("-topmost", True)
            dlg.deiconify(); dlg.lift(); dlg.focus_force()

            tk.Label(dlg, text="Do you want to exit ScreenRotator?",
                     font=("Arial", 11, "bold"), bg=BG_COLOR, fg=FG_COLOR
                     ).pack(pady=(22, 4))
            tk.Label(dlg, text="All rotation shortcuts will stop. Restart to restore.",
                     wraplength=310, justify="center",
                     bg=BG_COLOR, fg="#AAAAAA").pack(pady=4)

            row = tk.Frame(dlg, bg=BG_COLOR); row.pack(pady=16)

            def _yes():
                dlg.destroy()
                if self.icon:
                    self.icon.stop()
                os._exit(0)

            tk.Button(row, text="Yes, Exit", width=11, command=_yes,
                      bg="#992222", fg=FG_COLOR, relief="flat").pack(side="left",  padx=10)
            tk.Button(row, text="Cancel",    width=11, command=dlg.destroy,
                      bg=BTN_BG,   fg=FG_COLOR, relief="flat").pack(side="right", padx=10)

        self._tk_root.after(0, _create)

    # ── How to Use  (blank/reopen bug fixed) ─────────────────────────────────

    def show_instructions(self) -> None:
        """
        Bug fix: previous version could render blank or refuse to reopen.
        Root cause: stale Toplevel reference kept the lock held after the
        window was destroyed externally, and Label content was packed into
        a frame that was never realised before the geometry call.

        Fix: the lock is always released in a destroy-bound callback;
        all content is built inside a fresh scrollable Canvas so layout
        never clips silently; update_idletasks() is called before deiconify.
        """
        def _create():
            if not self._instructions_lock.acquire(blocking=False):
                return

            win = self._make_toplevel()

            def _close():
                try:
                    win.destroy()
                except Exception:
                    pass
                finally:
                    # Always release, even if window was force-closed
                    if self._instructions_lock.locked():
                        self._instructions_lock.release()

            # Wire the lock-release to all close paths
            win.protocol("WM_DELETE_WINDOW", _close)

            self.apply_custom_title_bar(win, "How to Use", SHORTCUT_LOGO_PATH,
                                         on_close_cb=_close)
            win.attributes("-topmost", True)

            # ── Scrollable content area ──────────────────────────────────────
            # Using a Canvas + inner Frame prevents blank-render bugs caused by
            # pack geometry being calculated before the window is visible.
            canvas = tk.Canvas(win, bg=BG_COLOR, highlightthickness=0,
                               borderwidth=0)
            scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview,
                                     bg=BTN_BG, troughcolor=HEADER_COLOR)
            canvas.configure(yscrollcommand=scrollbar.set)

            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            inner = tk.Frame(canvas, bg=BG_COLOR)
            inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

            def _on_inner_configure(_e):
                canvas.configure(scrollregion=canvas.bbox("all"))

            def _on_canvas_configure(e):
                canvas.itemconfig(inner_id, width=e.width)

            inner.bind("<Configure>", _on_inner_configure)
            canvas.bind("<Configure>", _on_canvas_configure)
            canvas.bind_all("<MouseWheel>",
                            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

            # ── Content ──────────────────────────────────────────────────────
            pad = dict(bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 10), justify="left")

            def section(title_str):
                tk.Label(inner, text=title_str,
                         bg=BG_COLOR, fg=ACCENT_COLOR,
                         font=("Arial", 10, "bold")).pack(anchor="w", padx=22, pady=(14, 2))

            def body(text_str):
                tk.Label(inner, text=text_str, **pad,
                         wraplength=430).pack(anchor="w", padx=28, pady=1)

            # About
            section("About ScreenRotator Auto")
            body("Developed for tactical and professional users to provide a seamless, "
                 "quick way to manage display orientation via keyboard macros.")

            # Instructions
            section("Instructions")
            steps = [
                "Use your assigned Hotkeys to rotate the screen instantly.",
                "Default trigger: Ctrl + Alt + [Arrow Key]  (system-wide / global).",
                "Open Settings to customise hotkeys and choose 'Max Keys' (1\u20135).",
                "Click 'Delete' to wipe an existing bind and record a fresh one.",
                "Click 'Add' to keep the current bind and append an extra key.",
                "Click 'Save Changes' to commit and activate your new hotkeys.",
                "Use 'Create Desktop Shortcut' or 'Add to Startup' from Settings.",
            ]
            for i, s in enumerate(steps, 1):
                body(f"{i}. {s}")

            # Orientation reference
            section("Orientation Reference")
            orientations = [
                ("Ctrl+Alt+\u2191  Up",    "Landscape          \u2014 0\u00b0   (default)"),
                ("Ctrl+Alt+\u2192  Right", "Portrait           \u2014 90\u00b0  (CW)"),
                ("Ctrl+Alt+\u2193  Down",  "Landscape Flipped  \u2014 180\u00b0"),
                ("Ctrl+Alt+\u2190  Left",  "Portrait Flipped   \u2014 270\u00b0 (CCW)"),
            ]
            for hotkey, desc in orientations:
                row = tk.Frame(inner, bg=BG_COLOR)
                row.pack(anchor="w", padx=28, pady=1)
                tk.Label(row, text=hotkey, bg=BG_COLOR, fg=LINK_COLOR,
                         font=("Consolas", 9), width=20, anchor="w").pack(side="left")
                tk.Label(row, text=desc,   bg=BG_COLOR, fg=FG_COLOR,
                         font=("Arial", 9), anchor="w").pack(side="left")

            # Project origins
            section("Project Origins")
            body("ScreenRotator was designed and developed by")

            author_row = tk.Frame(inner, bg=BG_COLOR)
            author_row.pack(anchor="w", padx=28, pady=(0, 2))
            author_lbl = tk.Label(author_row, text=APP_AUTHOR,
                                  fg=LINK_COLOR, bg=BG_COLOR,
                                  font=("Arial", 10, "underline"), cursor="hand2")
            author_lbl.pack(side="left")
            author_lbl.bind("<Button-1>", lambda _e: webbrowser.open(APP_GITHUB_URL))
            tk.Label(author_row, text=" as an open-source utility for Windows.",
                     bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 10)).pack(side="left")

            body("Development history: the project began as a personal utility "
                 "to solve the lack of a fast, keyboard-driven screen rotator on "
                 "Windows, and grew into a fully featured tray application with "
                 "configurable hotkeys, startup integration, and a modern dark UI.")

            # Got it button
            tk.Button(inner, text="Got it", command=_close,
                      width=16, bg=ACCENT_COLOR, fg=FG_COLOR,
                      relief="flat", pady=5).pack(pady=(16, 20))

            # ── Finalise geometry AFTER all widgets are packed ────────────────
            inner.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            self.center_window(win, 500, 540)
            win.deiconify()
            win.lift()
            win.focus_force()

        self._tk_root.after(0, _create)

    # ── Settings (deferred save) ──────────────────────────────────────────────

    def show_settings(self, block: bool = False) -> None:
        """
        Settings window.

        DEFERRED SAVE MODEL:
          • All edits (Add/Delete/capture) update a local *pending* dict only.
          • self.hotkeys (live) is NOT touched until the user clicks Save.
          • Closing the window without saving triggers an "unsaved changes"
            warning dialog that offers Save / Discard / Cancel.
          • On Save: pending is committed to self.hotkeys, written to disk,
            and hotkeys are re-registered thread-safely.
        """
        def _create():
            if not self._settings_lock.acquire(blocking=False):
                return

            # Pending dict — starts as a deep copy of the committed hotkeys
            pending: dict = copy.deepcopy(self.hotkeys)
            dirty_flag    = [False]     # list so inner functions can mutate it

            win = self._make_toplevel()
            win.attributes("-topmost", True)

            # ── Unsaved-changes guard ─────────────────────────────────────────
            def _close_requested():
                """Called by ✕ button, Close button, and WM_DELETE_WINDOW."""
                if dirty_flag[0]:
                    _show_unsaved_dialog()
                else:
                    _discard_and_close()

            def _discard_and_close():
                try:
                    win.destroy()
                except Exception:
                    pass
                finally:
                    if self._settings_lock.locked():
                        self._settings_lock.release()

            def _save_and_close():
                self._commit_and_save(pending)
                dirty_flag[0] = False
                try:
                    win.destroy()
                except Exception:
                    pass
                finally:
                    if self._settings_lock.locked():
                        self._settings_lock.release()

            def _show_unsaved_dialog():
                """Non-modal warning for unsaved changes."""
                dlg = tk.Toplevel(win)
                dlg.withdraw()
                dlg.configure(bg=BG_COLOR)
                set_icon_on_window(dlg)
                self.apply_custom_title_bar(dlg, "Unsaved Changes",
                                             on_close_cb=dlg.destroy)
                dlg.attributes("-topmost", True)
                self.center_window(dlg, 360, 175)
                dlg.deiconify(); dlg.lift(); dlg.focus_force()
                dlg.grab_set()

                tk.Label(dlg,
                         text="You have unsaved changes.",
                         font=("Arial", 11, "bold"), bg=BG_COLOR, fg=WARN_COLOR
                         ).pack(pady=(20, 4))
                tk.Label(dlg,
                         text="Save before closing, or discard your changes?",
                         wraplength=310, justify="center",
                         bg=BG_COLOR, fg="#AAAAAA").pack(pady=4)

                row = tk.Frame(dlg, bg=BG_COLOR); row.pack(pady=14)

                def _do_save():
                    dlg.destroy()
                    _save_and_close()

                def _do_discard():
                    dlg.destroy()
                    _discard_and_close()

                tk.Button(row, text="Save & Close", width=12, command=_do_save,
                          bg=ACCENT_COLOR, fg=FG_COLOR, relief="flat"
                          ).pack(side="left", padx=6)
                tk.Button(row, text="Discard",      width=10, command=_do_discard,
                          bg="#992222",    fg=FG_COLOR, relief="flat"
                          ).pack(side="left", padx=6)
                tk.Button(row, text="Cancel",       width=10, command=dlg.destroy,
                          bg=BTN_BG,       fg=FG_COLOR, relief="flat"
                          ).pack(side="left", padx=6)

            win.protocol("WM_DELETE_WINDOW", _close_requested)
            self.apply_custom_title_bar(win, "ScreenRotator Settings",
                                         SHORTCUT_LOGO_PATH,
                                         on_close_cb=_close_requested)

            # ── Header ────────────────────────────────────────────────────────
            hdr = tk.Frame(win, bg=BG_COLOR); hdr.pack(pady=(14, 0))
            tk.Label(hdr, text="Screen Rotation Controls",
                     font=("Arial", 14, "bold"), bg=BG_COLOR, fg=FG_COLOR
                     ).pack(side="left")
            tk.Label(hdr, text="   ScreenRotator is \U0001f534 Live",
                     font=("Arial", 9), bg=BG_COLOR, fg=LIVE_COLOR
                     ).pack(side="left", padx=12)

            # ── Hotkey rows ───────────────────────────────────────────────────
            self.key_labels = {}
            self.num_cells  = {}

            for direction, display_name in DIRECTION_DISPLAY.items():
                row = tk.Frame(win, bg=BG_COLOR)
                row.pack(pady=7, fill="x", padx=28)

                left = tk.Frame(row, bg=BG_COLOR); left.pack(side="left")
                tk.Label(left, text="\u25cf", fg=LIVE_COLOR,
                         bg=BG_COLOR).pack(side="left", padx=(0, 4))

                lbl = tk.Label(left,
                               text=f"{display_name}: {pending[direction]}",
                               width=34, anchor="w", bg=BG_COLOR, fg=FG_COLOR,
                               font=("Arial", 9))
                lbl.pack(side="left")
                self.key_labels[direction] = lbl

                spin = tk.Spinbox(row, from_=1, to=5, width=3,
                                  bg="#444", fg=FG_COLOR, relief="flat")
                spin.delete(0, "end"); spin.insert(0, "3")
                spin.pack(side="right", padx=4)
                self.num_cells[direction] = spin
                tk.Label(row, text="Max Keys:", bg=BG_COLOR,
                         fg="#888", font=("Arial", 8)).pack(side="right")

                tk.Button(
                    row, text="Delete", bg="#552222", fg=FG_COLOR,
                    relief="flat", font=("Arial", 8),
                    command=lambda d=direction: (
                        self.show_status_notification(
                            win,
                            f"Recording replacement for {DIRECTION_DISPLAY[d]}\u2026",
                            "#883300"),
                        self._capture_key_pending(d, win, pending,
                                                   dirty_flag, append=False)
                    )
                ).pack(side="right", padx=2)

                tk.Button(
                    row, text="Add", bg=BTN_BG, fg=FG_COLOR,
                    relief="flat", font=("Arial", 8),
                    command=lambda d=direction: (
                        self.show_status_notification(
                            win,
                            f"Appending key for {DIRECTION_DISPLAY[d]}\u2026",
                            BTN_BG),
                        self._capture_key_pending(d, win, pending,
                                                   dirty_flag, append=True)
                    )
                ).pack(side="right", padx=2)

            # ── Action buttons ────────────────────────────────────────────────
            tk.Button(win, text="Save Changes",
                      command=_save_and_close,
                      bg=ACCENT_COLOR, fg=FG_COLOR,
                      font=("Arial", 10, "bold"),
                      width=25, relief="flat", pady=7).pack(pady=(10, 4))

            tk.Label(win, text="System Options:", bg=BG_COLOR,
                     fg="#888").pack(pady=(10, 0))
            tk.Button(win, text="Create Desktop Shortcut",
                      command=lambda: [create_shortcut(),
                                       self.show_toast("Shortcut Created!")],
                      bg=BTN_BG, fg=FG_COLOR, width=25,
                      relief="flat", pady=4).pack(pady=3)
            tk.Button(win, text="Add to Startup",
                      command=lambda: [add_to_startup(),
                                       self.show_toast("Added to Startup!")],
                      bg=BTN_BG, fg=FG_COLOR, width=25,
                      relief="flat", pady=4).pack(pady=3)

            tk.Button(win, text="Close Window",
                      command=_close_requested,
                      bg="#444", fg=FG_COLOR, width=25,
                      relief="flat").pack(pady=(7, 0))

            # ── Footer ────────────────────────────────────────────────────────
            tk.Label(win, text=FOOTER_TEXT,
                     font=("Arial", 8), bg=BG_COLOR, fg="#666666"
                     ).pack(side="bottom", fill="x", pady=(0, 7))

            # ── Finalise ──────────────────────────────────────────────────────
            self.center_window(win, 640, 690)
            win.deiconify(); win.lift(); win.focus_force()

        if block:
            self._tk_root.after(0, _create)
            # Spin until window is opened then closed (second-instance path)
            while True:
                if self._settings_lock.acquire(blocking=False):
                    self._settings_lock.release()
                    break
                time.sleep(0.05)
        else:
            self._tk_root.after(0, _create)

    # ── Key capture (pending model) ───────────────────────────────────────────

    def _capture_key_pending(self, direction: str, parent: tk.BaseWidget,
                              pending: dict, dirty_flag: list,
                              append: bool = False) -> None:
        """
        Open the key-recording overlay.
        Writes the captured combo into *pending* (not self.hotkeys) so the
        change is staged until the user explicitly clicks Save Changes.
        """
        current_keys = pending[direction].split("+")
        max_allowed  = int(self.num_cells[direction].get())

        if append and len(current_keys) >= 5:
            self.show_status_notification(
                parent, "Limit reached \u2014 max 5 keys per hotkey.", "#992222")
            return

        cap = tk.Toplevel(parent)
        cap.withdraw()
        set_icon_on_window(cap)
        cap.configure(bg=BG_COLOR)
        self.apply_custom_title_bar(cap, "Recording Key")
        self.center_window(cap, 330, 230)
        cap.attributes("-topmost", True)
        cap.deiconify(); cap.lift(); cap.focus_force()
        cap.grab_set()

        mode_text = (
            f"Append key for  {DIRECTION_DISPLAY[direction]}\u2026"
            if append else
            f"New hotkey for  {DIRECTION_DISPLAY[direction]}\u2026"
        )
        tk.Label(cap, text=mode_text, bg=BG_COLOR, fg=FG_COLOR,
                 font=("Arial", 10, "bold"), wraplength=290).pack(pady=(22, 4))

        countdown_var = tk.StringVar(value="3")
        tk.Label(cap, textvariable=countdown_var, bg=BG_COLOR,
                 fg=LIVE_COLOR, font=("Arial", 22, "bold")).pack(pady=4)

        def _cancel():
            if cap.winfo_exists():
                cap.grab_release()
                cap.destroy()
            try:
                keyboard.send("f24")
            except Exception:
                pass

        def _tick(n):
            if not cap.winfo_exists():
                return
            if n > 0:
                countdown_var.set(str(n))
                cap.after(1000, _tick, n - 1)
            else:
                _cancel()

        _tick(3)
        tk.Button(cap, text="Cancel", command=_cancel,
                  bg="#444", fg=FG_COLOR, relief="flat",
                  padx=22, pady=4).pack(pady=10)
        cap.update_idletasks()

        def _reader():
            with self._hotkey_mutex:
                try:
                    keyboard.unhook_all()
                except Exception:
                    pass
                new_key = keyboard.read_hotkey(suppress=True)

            def _apply():
                if not cap.winfo_exists():
                    return
                if new_key and "f24" not in new_key.lower():
                    if append:
                        parts     = list(dict.fromkeys(current_keys + new_key.split("+")))
                        final_key = "+".join(parts[:5])
                    else:
                        final_key = "+".join(new_key.split("+")[:max_allowed])
                    # Stage into pending only
                    pending[direction] = final_key
                    dirty_flag[0] = True
                    self.key_labels[direction].config(
                        text=f"{DIRECTION_DISPLAY[direction]}: {final_key}")
                try:
                    cap.grab_release()
                    cap.destroy()
                except Exception:
                    pass
                # Re-register the LIVE (committed) hotkeys, not pending
                self.start_hotkeys()

            cap.after(0, _apply)

        threading.Thread(target=_reader, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Stand-alone helpers
# ─────────────────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def run_as_admin() -> None:
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1)


def create_tray_icon() -> Image.Image:
    """Return the best available image for the system tray icon."""
    for path in (ICO_PATH, SHORTCUT_LOGO_PATH, LOGO_PATH):
        if os.path.exists(path):
            return Image.open(path)
    # Fallback: solid dark square
    return Image.new("RGB", (64, 64), color=(33, 33, 33))


def create_shortcut() -> None:
    """Place a .lnk shortcut on the Desktop with the .ico icon."""
    desktop  = winshell.desktop()
    lnk_path = os.path.join(desktop, "ScreenRotator.lnk")
    shell    = Dispatch("WScript.Shell")
    sc       = shell.CreateShortCut(lnk_path)
    sc.Targetpath       = sys.executable
    sc.WorkingDirectory = os.path.dirname(sys.executable)
    if os.path.exists(ICO_PATH):
        sc.IconLocation = os.path.abspath(ICO_PATH)
    elif os.path.exists(LOGO_PATH):
        sc.IconLocation = os.path.abspath(LOGO_PATH)
    sc.save()


def add_to_startup() -> None:
    """Register the app as a scheduled task on user logon (elevated)."""
    cmd = [
        "schtasks", "/create", "/f",
        "/tn", TASK_NAME,
        "/tr", f'"{sys.executable}"',
        "/sc", "onlogon",
        "/rl", "highest",
    ]
    subprocess.run(cmd, shell=True)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # Ensure we run elevated (hotkey suppression requires admin on some systems)
    if not is_admin():
        run_as_admin()
        sys.exit(0)

    # Single-instance guard via named mutex
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "Global\\ScreenRotator_Unique_Mutex")
    if kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        # Another instance running — open Settings in this second process
        app_tmp = RotatorApp()
        app_tmp.show_settings(block=True)
        sys.exit(0)

    app = RotatorApp()
    app.show_toast("ScreenRotator is \U0001f534 Live")

    # First-run setup
    if not os.path.exists(CONFIG_PATH):
        create_shortcut()
        add_to_startup()
        app._commit_and_save(app.hotkeys)   # write defaults to disk
        app.show_instructions()

    app.start_hotkeys()

    menu = Menu(
        MenuItem("Settings",   lambda _i, _it: app.show_settings()),
        MenuItem("How to Use", lambda _i, _it: app.show_instructions()),
        MenuItem("Exit",       lambda _i, _it: app.confirm_exit()),
    )
    app.icon = Icon("ScreenRotator", create_tray_icon(), menu=menu)
    app.icon.run()


if __name__ == "__main__":
    main()