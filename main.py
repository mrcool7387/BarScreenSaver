import ctypes
import json
import math
import os
import queue
import threading
import time
import tkinter.simpledialog
from ctypes import windll
from datetime import datetime

import comtypes
import customtkinter as ctk
import numpy as np
import win32con
import win32gui
import win32process
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation, ISimpleAudioVolume

import _template

# -----------------------
# CONFIG
# -----------------------
if not os.path.exists("config.json"):
    default_config = {
        "bar_count": 32,
        "bar_color": "#66CCFF",
        "background_color": "#111111",
        "mirror_bars": True,
        "update_rate": 30,
        "show_clock": True,
    }
    with open("config.json", "w") as f:
        json.dump(default_config, f, indent=4)

with open("config.json", "r") as f:
    CONFIG = json.load(f)

BAR_COUNT = CONFIG.get("bar_count", 32)
BAR_COLOR = CONFIG.get("bar_color", "#66CCFF")
BG_COLOR = CONFIG.get("background_color", "#111111")
MIRROR = CONFIG.get("mirror_bars", True)
FPS = CONFIG.get("update_rate", 30)
SHOW_CLOCK = CONFIG.get("show_clock", True)
SMOOTHING = CONFIG.get("smoothing", 0.6)
# Gradient config: when true, bars are rendered with a left->right gradient
GRADIENT = CONFIG.get("gradient", False)
GRADIENT_START = CONFIG.get("gradient_start", BAR_COLOR)
GRADIENT_END = CONFIG.get("gradient_end", BAR_COLOR)
# Number of vertical slices per bar to approximate a horizontal gradient
GRADIENT_SLICES = CONFIG.get("gradient_slices", 8)

# Optional: restrict media-title lookup to a specific process id (pid)
SELECT_PID = None

l = _template.LOGGER
l.info(f"Configuration loaded: {CONFIG}")

# -----------------------
# Advertisement detection keywords
# -----------------------
AD_KEYWORDS = CONFIG.get("ad_keywords", [])

def is_advertisement(text):
    """Check if text contains advertisement keywords (case-insensitive)."""
    if not text:
        return False
    text_lower = str(text).lower().strip()
    return any(keyword in text_lower for keyword in AD_KEYWORDS)


# -----------------------
# Audio capture
# -----------------------
def mute_all_audio(muted=True):
    """Mute or unmute all audio sessions."""
    try:
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            try:
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                volume.SetMute(muted, None)
                l.debug(f"Audio session muted={muted}")
            except Exception as e:
                l.debug(f"Failed to mute session: {e}")
    except Exception as e:
        l.exception(f"mute_all_audio: error: {e}")


class AudioCapture(threading.Thread):
    def __init__(self, q: queue.Queue):
        super().__init__(daemon=True)
        self.q = q
        self.running = True

    def run(self):
        # Initialize COM for this thread so pycaw/comtypes calls succeed.
        # CoInitialize must be paired with CoUninitialize when the thread exits.
        l.debug("AudioCapture: initializing COM in audio thread")
        comtypes.CoInitialize()
        try:
            l.info("AudioCapture: thread started")
            while self.running:
                try:
                    sessions = AudioUtilities.GetAllSessions()
                    l.debug(f"AudioCapture: found {len(sessions)} sessions")
                    levels = []
                    for session in sessions:
                        try:
                            meter = session._ctl.QueryInterface(IAudioMeterInformation)
                            val = meter.GetPeakValue()
                            levels.append(val)
                        except Exception as e:
                            l.debug(
                                f"AudioCapture: failed to read meter for session: {e}"
                            )
                    if levels:
                        max_level = max(levels)
                        l.debug(f"AudioCapture: max level={max_level:.4f}")
                        # FFT-like random distribution to bars
                        spectrum = np.random.rand(BAR_COUNT) * max_level
                        self.q.put(spectrum)
                    else:
                        l.debug("AudioCapture: no levels detected, pushing zeros")
                        self.q.put(np.zeros(BAR_COUNT))
                except Exception as e:
                    l.exception(f"AudioCapture: unexpected error in audio loop: {e}")
                time.sleep(1 / FPS)
        finally:
            comtypes.CoUninitialize()
            l.info("AudioCapture: COM uninitialized and thread exiting")

    def stop(self):
        self.running = False


# -----------------------
# Media info (Fenster-Titel)
# -----------------------
def get_media_info():
    titles = []

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                pid = None

            # If a specific PID is selected, prefer windows owned by that PID.
            if SELECT_PID is not None:
                if pid == SELECT_PID and title:
                    titles.append(title)
            else:
                if title and any(
                    p in title.lower()
                    for p in ["spotify", "youtube", "vlc", "music", "mpv", "media"]
                ):
                    titles.append(title)

    win32gui.EnumWindows(enum_handler, None)
    l.debug(f"get_media_info: candidate titles={titles} (SELECT_PID={SELECT_PID})")

    if not titles:
        l.debug("get_media_info: no media window titles found")
        return "Kein Titel", "Keine Wiedergabe", ""

    title = titles[0]
    # Many windows use "Artist - Title" or "Title - Artist". Try to be flexible.
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) >= 2:
            # Heuristic: if the first part contains known artist words (lowercase check), guess format Artist - Title
            first, second = parts[0].strip(), " - ".join(parts[1:]).strip()
            l.debug(
                f"get_media_info: parsed as title/artist -> title='{first}', artist='{second}'"
            )
            return first, second, None
    l.debug(f"get_media_info: returning raw title='{title}'")
    return title, None, None


# -----------------------
# GUI
# -----------------------
class Visualizer(ctk.CTk):
    def __init__(self, audio_queue):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.audio_queue = audio_queue
        self.bars = np.zeros(BAR_COUNT)
        self.target = np.zeros_like(self.bars)
        self.current_title = None
        self.current_artist = None
        self.is_ad_playing = False
        # always define time_label attribute to satisfy runtime and static checks
        self.time_label = None

        # Set up window with normal borders
        self.title("Audio Visualizer")

        # Set a reasonable default window size
        width, height = 1024, 600
        self.geometry(f"{width}x{height}")

        # Center the window on screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"+{x}+{y}")

        # Allow window resizing
        self.resizable(True, True)

        # Canvas
        self.canvas = ctk.CTkCanvas(self, highlightthickness=0, bg=BG_COLOR)
        self.canvas.pack(fill="both", expand=True)

        # Bind F8 to reload config and rebuild UI
        # use bind_all so it works regardless of which widget has focus
        try:
            self.bind_all("<F8>", lambda e: self.reload_config())
            l.info("Visualizer: F8 bound to config reload")
        except Exception:
            l.exception("Visualizer: failed to bind F8 key")

        # Pre-create bar items and handle resizing to avoid creating/deleting shapes each frame
        self.bar_items = []
        self.mirror_items = []
        # Bind resize so we can recalc geometry
        self.canvas.bind("<Configure>", self._on_resize)

        # Labels - create a frame to hold them and center on canvas
        self.info_frame = ctk.CTkFrame(self.canvas, fg_color=BG_COLOR)
        self.info_window = self.canvas.create_window(0, 80, window=self.info_frame, anchor="center", tags="info_frame")
        
        if SHOW_CLOCK:
            self.time_label = ctk.CTkLabel(
                self.info_frame, text="", font=("Segoe UI", 32, "bold"), bg_color=BG_COLOR
            )
            self.time_label.pack()
        self.title_label = ctk.CTkLabel(
            self.info_frame,
            text="Titel — Artist",
            font=("Segoe UI", 20),
            bg_color=BG_COLOR,
            text_color="#FFFFFF",
        )
        self.title_label.pack()
        self.desc_label = ctk.CTkLabel(
            self.info_frame,
            text="",
            font=("Segoe UI", 14),
            bg_color=BG_COLOR,
            text_color="#DDDDDD",
        )
        self.desc_label.pack()

        # Ad indicator label in bottom right corner
        self.ad_indicator = ctk.CTkLabel(
            self.canvas,
            text="🔇 AD",
            font=("Segoe UI", 20, "bold"),
            bg_color=BG_COLOR,
            text_color="#FF4444",
        )
        self.ad_indicator_window = None

        l.debug("Visualizer: UI initialized")

        self.update_ui()
        self.update_visuals()

        # Check if gradient premade is enabled
        if CONFIG.get('gradient_premaide', False) and CONFIG.get('gradient', False):
            # Ask for gradient selection
            gradient_choice = ctk.CTkOptionMenu(self, options=['spring', 'summer', 'autumn', 'winter'], command=self.apply_gradient)
            gradient_choice.pack()  # Add to the GUI layout

    def reload_config(self, event=None):
        """Reload configuration from config.json and rebuild the UI accordingly.

        This updates module-level config variables, resizes internal buffers,
        recreates the bar items, updates colors and clock visibility, and
        logs any errors. Intended to be called on F8 press.
        """
        global CONFIG, BAR_COUNT, BAR_COLOR, BG_COLOR, MIRROR, FPS, SHOW_CLOCK
        global GRADIENT, GRADIENT_START, GRADIENT_END, GRADIENT_SLICES
        try:
            l.info("reload_config: reloading config.json")
            with open("config.json", "r") as f:
                CONFIG = json.load(f)

            # Update module globals
            BAR_COUNT = CONFIG.get("bar_count", BAR_COUNT)
            BAR_COLOR = CONFIG.get("bar_color", BAR_COLOR)
            BG_COLOR = CONFIG.get("background_color", BG_COLOR)
            MIRROR = CONFIG.get("mirror_bars", MIRROR)
            FPS = CONFIG.get("update_rate", FPS)
            SHOW_CLOCK = CONFIG.get("show_clock", SHOW_CLOCK)
            GRADIENT = CONFIG.get("gradient", GRADIENT)
            GRADIENT_START = CONFIG.get("gradient_start", GRADIENT_START)
            GRADIENT_END = CONFIG.get("gradient_end", GRADIENT_END)
            GRADIENT_SLICES = CONFIG.get("gradient_slices", GRADIENT_SLICES)

            l.info(f"reload_config: new config={CONFIG}")

            # Update canvas background
            try:
                self.canvas.configure(bg=BG_COLOR)
            except Exception:
                l.exception("reload_config: failed to set canvas background color")

            # Resize internal arrays (bars/target)
            try:
                self.bars = np.zeros(BAR_COUNT)
                self.target = np.zeros_like(self.bars)
            except Exception:
                l.exception("reload_config: failed to resize bars arrays")

            # Recreate bar items to match new BAR_COUNT and colors
            try:
                self._init_bars()
                # Update fill color for bars tag (in case color changed)
                try:
                    self.canvas.itemconfig("bars", fill=BAR_COLOR)
                except Exception:
                    # Not critical; itemconfig may fail if items haven't been created
                    l.debug("reload_config: itemconfig for bars failed (maybe no items yet)")
            except Exception:
                l.exception("reload_config: failed to reinitialize bar items")

            # Show/hide clock label depending on SHOW_CLOCK
            try:
                if SHOW_CLOCK:
                    if not hasattr(self, "time_label") or self.time_label is None:
                        self.time_label = ctk.CTkLabel(
                            self.info_frame, text="", font=("Segoe UI", 32, "bold"), bg_color=BG_COLOR
                        )
                        self.time_label.pack(before=self.title_label)
                else:
                    if hasattr(self, "time_label") and self.time_label is not None:
                        try:
                            self.time_label.destroy()
                        except Exception:
                            pass
                        self.time_label = None
            except Exception:
                l.exception("reload_config: failed to update clock visibility")

            # Update label colors/background if needed
            try:
                # CTk uses configure for label colors as well
                self.title_label.configure(text_color="#FFFFFF")
                self.desc_label.configure(text_color="#DDDDDD")
            except Exception:
                l.debug("reload_config: failed to reconfigure labels")

            # Force a redraw by calling the resize handler and updating visuals once
            try:
                self._on_resize(type("E", (), {"width": self.winfo_width(), "height": self.winfo_height()}))
            except Exception:
                # If our synthetic event fails, just call _init_bars as fallback
                try:
                    self._init_bars()
                except Exception:
                    l.exception("reload_config: fallback _init_bars also failed")

            l.info("reload_config: config reloaded and UI rebuilt")
        except Exception as e:
            l.exception(f"reload_config: failed to reload config: {e}")

    def update_ui(self):
        # Only update the clock label if the config requests it and the label exists
        time_lbl = getattr(self, "time_label", None)
        if SHOW_CLOCK and time_lbl is not None:
            time_lbl.configure(text=datetime.now().strftime("%d.%m.%Y   %H:%M:%S"))
        title, artist, desc = get_media_info()
        
        # Check if current media is an advertisement
        is_currently_ad = is_advertisement(title) or is_advertisement(artist) or is_advertisement(desc)
        
        # Handle muting/unmuting
        if is_currently_ad and not self.is_ad_playing:
            l.info(f"Advertisement detected: title='{title}' artist='{artist}'")
            mute_all_audio(muted=True)
            self.is_ad_playing = True
            # Show ad indicator
            if self.ad_indicator_window is None:
                width = self.winfo_width() or 800
                height = self.winfo_height() or 600
                self.ad_indicator_window = self.canvas.create_window(
                    width - 50, height - 30, window=self.ad_indicator, anchor="se", tags="ad_indicator"
                )
        elif not is_currently_ad and self.is_ad_playing:
            l.info("Advertisement ended, unmuting audio")
            mute_all_audio(muted=False)
            self.is_ad_playing = False
            # Hide ad indicator
            if self.ad_indicator_window is not None:
                try:
                    self.canvas.delete(self.ad_indicator_window)
                except Exception:
                    pass
                self.ad_indicator_window = None
        
        # Log changes only
        if title != self.current_title or artist != self.current_artist:
            l.info(
                f"Visualizer: media changed -> title='{title}' artist='{artist}' desc='{desc}'"
            )
            self.current_title = title
            self.current_artist = artist

        self.title_label.configure(text=f"{title} — {artist}" if artist else title)
        self.desc_label.configure(text=desc or "")
        self.after(500, self.update_ui)

    def draw_bars(self, spectrum):
        # Update existing rectangle coords instead of deleting/creating them each frame.
        width = self.winfo_width()
        height = self.winfo_height()
        mid = height // 2
        bar_w = width / (BAR_COUNT * 1.5)
        # Ensure we have items created (first configure event should create them)
        if not self.bar_items:
            self._init_bars()

        for i in range(BAR_COUNT):
            val = float(self.bars[i])
            h = val * mid * 0.9
            x = i * bar_w * 1.5 + bar_w
            x1, y1, x2, y2 = x, mid - h, x + bar_w, mid
            try:
                # In gradient mode each bar has its own stepped color but is still a single rectangle
                self.canvas.coords(self.bar_items[i], x1, y1, x2, y2)
            except Exception:
                # If something unexpected happened (e.g., items not initialized), skip
                continue
            if MIRROR:
                try:
                    self.canvas.coords(self.mirror_items[i], x1, mid, x2, mid + h)
                except Exception:
                    continue

        # Keep tag for possible future operations
        # Note: avoid per-frame logging here to prevent slowdown


    def _init_bars(self):
        """Create rectangle items once. Called on first draw or on resize."""
        # Clear any existing items
        for item in self.bar_items + self.mirror_items:
            try:
                self.canvas.delete(item)
            except Exception:
                pass
        self.bar_items = []
        self.mirror_items = []

        width = self.winfo_width() or 800
        height = self.winfo_height() or 600
        mid = height // 2
        bar_w = width / (BAR_COUNT * 1.5)

        # Prepare color helpers once
        def hex_to_rgb(h):
            h = h.lstrip("#")
            return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

        def rgb_to_hex(r, g, b):
            return f"#{r:02X}{g:02X}{b:02X}"

        start_rgb = hex_to_rgb(GRADIENT_START)
        end_rgb = hex_to_rgb(GRADIENT_END)

        for i in range(BAR_COUNT):
            x = i * bar_w * 1.5 + bar_w
            # start with zero height rectangles centered at mid
            if GRADIENT:
                # compute stepped color for this bar across the full bar span
                t = i / max(1, BAR_COUNT - 1)
                r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
                g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
                b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
                color = rgb_to_hex(r, g, b)
                rect = self.canvas.create_rectangle(x, mid, x + bar_w, mid, fill=color, width=0, tags="bars")
                self.bar_items.append(rect)
                if MIRROR:
                    rect2 = self.canvas.create_rectangle(x, mid, x + bar_w, mid, fill=color, width=0, tags="bars")
                    self.mirror_items.append(rect2)
            else:
                rect = self.canvas.create_rectangle(x, mid, x + bar_w, mid, fill=BAR_COLOR, width=0, tags="bars")
                self.bar_items.append(rect)
                if MIRROR:
                    rect2 = self.canvas.create_rectangle(x, mid, x + bar_w, mid, fill=BAR_COLOR, width=0, tags="bars")
                    self.mirror_items.append(rect2)

    def _on_resize(self, event):
        """Handle canvas resize: recreate items to match new geometry."""
        # Recreate bar items to match new sizes; quick and infrequent (on resize only)
        self._init_bars()
        # Reposition info frame to center it horizontally
        self.canvas.coords(self.info_window, event.width // 2, 80)
        # Reposition ad indicator to bottom right
        if self.ad_indicator_window is not None and self.is_ad_playing:
            self.canvas.coords(self.ad_indicator_window, event.width - 50, event.height - 30)

    def update_visuals(self):
        while not self.audio_queue.empty():
            spectrum = self.audio_queue.get()
            self.target = spectrum
            l.debug("update_visuals: new spectrum dequeued and target updated")
        self.bars = SMOOTHING * self.bars + (1 - SMOOTHING) * self.target
        self.draw_bars(self.bars)
        self.after(int(1000 / FPS), self.update_visuals)

    # Function to apply selected gradient
    def apply_gradient(self, selected_gradient):
        global GRADIENT_START, GRADIENT_END
        GRADIENT_START = CONFIG['gradients'][selected_gradient][0]
        GRADIENT_END = CONFIG['gradients'][selected_gradient][1]
        l.info(f"Gradient applied: {selected_gradient}")


if __name__ == "__main__":
    # Ask the user for an optional PID to restrict media-title lookup.
    try:
        root = ctk.CTk()
        root.withdraw()
        pid_input = tkinter.simpledialog.askstring(
            "Media PID Filter",
            "Enter PID to restrict media lookup (leave blank to scan all):",
            parent=root,
        )
        if pid_input is None:
            pid_input = ""
        root.destroy()
    except Exception as e:
        l.debug(f"Main: input() failed or no console available: {e}")
        pid_input = ""

    if pid_input:
        try:
            SELECT_PID = int(pid_input)
            l.info(f"Main: restricting media lookup to PID {SELECT_PID}")
        except ValueError:
            l.warning(
                f"Main: invalid PID entered '{pid_input}', continuing without PID filter"
            )
            SELECT_PID = None

    q = queue.Queue()
    audio_thread = AudioCapture(q)
    try:
        l.info("Main: starting audio thread")
        audio_thread.start()

        app = Visualizer(q)
        l.info("Main: starting GUI mainloop")
        app.mainloop()
    except Exception as e:
        l.exception(f"Main: unhandled exception: {e}")
    finally:
        l.info("Main: stopping audio thread")
        audio_thread.stop()
        # Give the thread a moment to exit cleanly
        audio_thread.join(timeout=1.0)
        l.info("Main: exiting")
