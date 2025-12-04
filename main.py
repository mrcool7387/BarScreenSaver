import json
import math
import os
import queue
import threading
import time
from ctypes import windll
from datetime import datetime

import comtypes
import customtkinter as ctk
import numpy as np
# Removed windows-specific imports: win32con, win32gui, win32process
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation, ISimpleAudioVolume

# New imports for Spotify logic
import http.server
import socketserver
import requests
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs

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
GRADIENT = CONFIG.get("gradient", False)
GRADIENT_START = CONFIG.get("gradient_start", BAR_COLOR)
GRADIENT_END = CONFIG.get("gradient_end", BAR_COLOR)
GRADIENT_SLICES = CONFIG.get("gradient_slices", 8)
DYNAMIC_GRADIENT = CONFIG.get("gradient_dynamic", False)
GRADIENT_SPEED = CONFIG.get("gradient_speed", 2.0)

# Optional: restrict media-title lookup to a specific process id (pid)
# SELECT_PID is now obsolete
SELECT_PID = None

l = _template.LOGGER
l.info(f"Configuration loaded: {CONFIG}")


# ---------------------------------------------------------
# 🛠️ SPOTIFY/GEMINI CONFIGURATION
# ---------------------------------------------------------
# NOTE: Replace these with your actual credentials
CLIENT_ID = "SPOTIFY_APP_CLIENT_ID"
CLIENT_SECRET = "SPOTIFY_APP_CLIENT_SECRET"
REDIRECT_URI = "http://127.0.0.1:8080/callback"
TOKEN_FILE = "spotify_token.json"

assert CLIENT_ID != "SPOTIFY_APP_CLIENT_ID", "Please set your Spotify App Client ID in Line 69:13."
assert CLIENT_SECRET != "SPOTIFY_APP_CLIENT_SECRET", "Please set your Spotify App Client Secret in Line 70:17."

# Scope updated to include 'user-read-recently-played' to access playback history
SCOPES = "user-read-currently-playing user-read-recently-played"

# Spotify API base URLs (using placeholders for security)
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_NOW_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"
SPOTIFY_RECENTLY_PLAYED_URL = "https://api.spotify.com/v1/me/player/recently-played"
SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"

# ---------------------------------------------------------
# 💾 Token Handling
# ---------------------------------------------------------
def save_tokens(data):
    """Saves the Spotify access and refresh tokens to a file."""
    l.debug("Saving Spotify tokens to file.")
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_tokens():
    """Loads existing Spotify tokens from the file."""
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            l.debug("Loading tokens from file.")
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        l.info("No token file found or file is invalid.")
        return None

# ---------------------------------------------------------
# 🔒 OAuth Flow and Server
# ---------------------------------------------------------
auth_code = None

class OAuthHandler(http.server.SimpleHTTPRequestHandler):
    """Handles the temporary local server to capture the OAuth callback."""
    def do_GET(self):
        global auth_code
        parsed_url = urlparse(self.path)
        
        if parsed_url.path == "/callback":
            query_params = parse_qs(parsed_url.query)
            if "code" in query_params:
                auth_code = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                msg = "Spotify login successful! You can close this window."
                self.wfile.write(msg.encode("utf-8"))
                l.info("Authorization code received and server closed.")
                return
        
        self.send_error(404)

def start_auth_server():
    """Starts a temporary HTTP server to capture the authorization code."""
    with socketserver.TCPServer(("127.0.0.1", 8080), OAuthHandler) as httpd:
        l.debug("Temporary HTTP server started on 127.0.0.1:8080.")
        # Only handle one request (the callback) and then shut down
        httpd.handle_request()

def initiate_auth_flow():
    """Starts the full authorization process."""
    l.info("Starting Spotify login...")
    
    # 1. Start the local server in a separate thread
    t = threading.Thread(target=start_auth_server)
    t.daemon = True
    t.start()
    
    # 2. Build and open the authorization URL
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES
    }
    auth_url = f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"
    webbrowser.open(auth_url)
    
    l.info("Please log in and grant access in the browser...")
    
    # 3. Wait for the authorization code
    global auth_code
    while auth_code is None:
        time.sleep(0.3)
        
    # 4. Exchange the code for tokens
    l.info("Exchanging authorization code for tokens.")
    tokens = get_tokens_from_code(auth_code)
    save_tokens(tokens)
    return tokens

def get_tokens_from_code(code):
    """Exchanges the authorization code for access and refresh tokens."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    r = requests.post(SPOTIFY_AUTH_URL, data=data)
    r.raise_for_status()
    l.debug("Successfully exchanged code for tokens.")
    return r.json()

def refresh_access_token(refresh_token):
    """Uses the refresh token to get a new access token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    r = requests.post(SPOTIFY_AUTH_URL, data=data)
    r.raise_for_status()
    l.info("Access token successfully refreshed.")
    return r.json()

# ---------------------------------------------------------
# 🎧 Spotify API Call Functions
# ---------------------------------------------------------
def get_current_playing(access_token):
    """Fetches the currently playing track."""
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(SPOTIFY_NOW_PLAYING_URL, headers=headers)
    
    # 204 No Content means nothing is currently playing
    if r.status_code == 204:
        l.debug("API Status: 204 No Content. Nothing is currently playing.")
        return None
    if r.status_code != 200:
        r.raise_for_status() # Raise error for other non-200 codes
        
    data = r.json()
    if not data.get("is_playing", False):
        l.debug("API Status: 200 OK, but 'is_playing' is false.")
        return None
        
    item = data.get("item")
    # We only care about tracks for the visualizer title
    if not item or item.get("type") != "track" or not item.get("artists"):
        l.debug("API Status: Current item is not a track (e.g., episode, context) or missing data.")
        return None 
        
    title = item["name"]
    artist = item["artists"][0]["name"]
    l.debug(f"API fetched: {title} by {artist}")
    return title, artist

# -----------------------
# Media info (Spotify API)
# -----------------------
class SpotifyMediaCapture(threading.Thread):
    def __init__(self, q: queue.Queue):
        super().__init__(daemon=True)
        self.q = q # The queue to send media info (title, artist, is_ad)
        self.running = True
        self.tokens = None
        self.access_token = None
        self.refresh_token = None
        self.last_song_checked = None

    def run(self):
        # --- Authentication Setup ---
        self.tokens = load_tokens()
        if not self.tokens:
            l.info("SpotifyMediaCapture: No tokens found, initiating auth flow.")
            self.tokens = initiate_auth_flow()
        else:
            l.info("SpotifyMediaCapture: Loaded existing tokens.")

        self.access_token = self.tokens["access_token"]
        self.refresh_token = self.tokens.get("refresh_token")
        l.info("SpotifyMediaCapture: Start monitoring...")
        
        self.auth_setup_complete = True
        
        while self.running:
            try:
                # 1. Get the current track
                current_song = get_current_playing(self.access_token)
                
                # --- Handle No Song or Token Error ---
                if current_song is None:
                    # CLASSIFICATION LOGIC: If no title/artist is available, assume it's an AD/Silence/Interlude.
                    is_ad = True 
                    title = "No Title / AD"
                    artist = "No Playback / AD"

                    # Attempt to refresh the token on any interruption or if nothing is playing
                    try:
                        refreshed = refresh_access_token(self.refresh_token)
                        self.access_token = refreshed["access_token"]
                        self.tokens["access_token"] = self.access_token
                        save_tokens(self.tokens)
                        l.debug("SpotifyMediaCapture: Status: No music active. Token refreshed.")
                    except Exception:
                        l.debug("SpotifyMediaCapture: Status: No music active or error during token refresh.")
                    
                    # Push default empty/ad state to the queue
                    if self.last_song_checked != (title, artist):
                        l.info("[Logic-Check] Classified as ADVERTISEMENT (No track data available).")
                        self.last_song_checked = (title, artist)
                    
                    self.q.put((title, artist, is_ad))
                    time.sleep(1)
                    continue
                    
                # --- Process Track ---
                title, artist = current_song
                # CLASSIFICATION LOGIC: If we have a title/artist, it is a Music Track.
                is_ad = False 
                
                # --- Log New Song ---
                if self.last_song_checked != (title, artist):
                    l.info(f"SpotifyMediaCapture: --- NEW TRACK ---: {title} - {artist}")
                    l.info("[Logic-Check] Classified as Music Track (Title/Artist available).")
                        
                    self.last_song_checked = (title, artist)
                    
                # Send the latest info to the GUI thread
                self.q.put((title, artist, is_ad))
                
            except requests.HTTPError as e:
                # Catch 401 Unauthorized or other HTTP errors
                l.error(f"SpotifyMediaCapture: ❌ HTTP Error ({e.response.status_code}): {e}")
                if e.response.status_code == 401:
                    # Token expired/invalid, try refresh immediately
                    l.warning("SpotifyMediaCapture: Attempting token refresh due to 401...")
                    try:
                        refreshed = refresh_access_token(self.refresh_token)
                        self.access_token = refreshed["access_token"]
                        self.tokens["access_token"] = self.access_token
                        save_tokens(self.tokens)
                        l.info("SpotifyMediaCapture: Token successfully refreshed. Continuing monitoring.")
                    except Exception as refresh_err:
                        l.exception(f"SpotifyMediaCapture: Error during token refresh: {refresh_err}. Exiting thread.")
                        self.q.put(("Token Error", "Re-Auth Required", True)) # Signal error
                        break # Exit loop if refresh fails
                
                self.q.put(("Error", f"HTTP {e.response.status_code}", True))
                    
            except Exception as e:
                l.exception(f"SpotifyMediaCapture: An unexpected error occurred: {e}")
                self.q.put(("Error", "Unknown Issue", True)) # Signal error
            
            # Wait before checking again
            time.sleep(1) # Check Spotify every 5 seconds
        
        l.info("SpotifyMediaCapture: thread exiting")
            
    def stop(self):
        self.running = False


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
# GUI
# -----------------------
class Visualizer(ctk.CTk):    
    def __init__(self, audio_queue, media_queue):
        # Fullscreen state and binding
        self.is_fullscreen = False
        super().__init__()
        self.bind_all("<F11>", self.toggle_fullscreen)
        self.bind_all("<F6>", self.force_mute)
        self.bind_all("<F7>", self.force_unmute)
        ctk.set_appearance_mode("dark")
        self.audio_queue = audio_queue
        self.media_queue = media_queue # New media queue
        self.bars = np.zeros(BAR_COUNT)
        self.target = np.zeros_like(self.bars)
        self.current_title = "No Title"
        self.current_artist = "No Playback"
        self.current_desc = ""
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
            text="Title — Artist",
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
        
        self.muted_indicator = ctk.CTkLabel(
            self.canvas,
            text="🔇 MUTED",
            font=("Segoe UI", 20, "bold"),
            bg_color=BG_COLOR,
            text_color="#FF4444",
        )
        self.muted_indicator_window = None

        # Timer label in bottom right corner (same place as ad indicator)
        self.timer_label = ctk.CTkLabel(
            self.canvas,
            text="📰 ??:??",
            font=("Segoe UI", 20, "bold"),
            bg_color=BG_COLOR,
            text_color="#44FF44",
        )
        self.timer_label_window = None
        self.timer_running = False
        self.timer_end_time = None
        self.timer_last_state = None  # None, 'ad', 'timer', 'blank'

        l.info("Visualizer: UI initialized")
        l.info(f"Visualizer: Bar Count: {BAR_COUNT}, FPS: {FPS}, Mirror: {MIRROR}")

        self.update_ui()
        self.update_visuals()

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        l.info(f"Fullscreen toggled: {self.is_fullscreen}")
        # Optionally, escape exits fullscreen
        if self.is_fullscreen:
            self.bind_all("<Escape>", self.exit_fullscreen)
        else:
            self.unbind_all("<Escape>")

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.attributes("-fullscreen", False)
        self.unbind_all("<Escape>")
        l.info("Exiting fullscreen.")

    def force_mute(self, event=None):
        mute_all_audio(muted=True)
        l.info("Force mute triggered (F6). Audio muted.")
        # Show Muted Indicator
        if self.muted_indicator_window is None:
            width = self.winfo_width() or 800
            height = self.winfo_height() or 600
            self.muted_indicator_window = self.canvas.create_window(
                width - 50, height - 110, window=self.muted_indicator, anchor="se", tags="muted_indicator"
            )

    def force_unmute(self, event=None):
        mute_all_audio(muted=False)
        l.info("Force unmute triggered (F7). Audio unmuted.")
        # Hide Muted Indicator
        if self.muted_indicator_window is not None:
            try:
                self.canvas.delete(self.muted_indicator_window)
            except Exception:
                pass
            self.muted_indicator_window = None

    def reload_config(self, event=None):
        """Reload configuration from config.json and rebuild the UI accordingly.
        """
        global CONFIG, BAR_COUNT, BAR_COLOR, BG_COLOR, MIRROR, FPS, SHOW_CLOCK
        global GRADIENT, GRADIENT_START, GRADIENT_END, GRADIENT_SLICES
        global DYNAMIC_GRADIENT, GRADIENT_SPEED
        
        try:
            l.info("Reloading config.json (F8 triggered).")
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
            GRADIENT_SPEED = CONFIG.get("gradient_speed", GRADIENT_SPEED)
            DYNAMIC_GRADIENT = CONFIG.get("gradient_dynamic", DYNAMIC_GRADIENT)

            l.info(f"New configuration loaded: Bar Count={BAR_COUNT}, FPS={FPS}, Mirror={MIRROR}")

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

            l.info("Config reloaded and UI rebuilt successfully.")
        except Exception as e:
            l.exception(f"reload_config: failed to reload config: {e}")

    def update_ui(self):
        # 1. Update clock
        time_lbl = getattr(self, "time_label", None)
        if SHOW_CLOCK and time_lbl is not None:
            time_lbl.configure(text=datetime.now().strftime("%d.%m.%Y   %H:%M:%S"))

        # 2. Get latest media info from the media thread queue
        while not self.media_queue.empty():
            try:
                title, artist, is_ad = self.media_queue.get_nowait()
                # Only update media info if it has changed
                if title != self.current_title or artist != self.current_artist:
                    l.info(
                        f"Visualizer: Media info updated: Title='{title}' Artist='{artist}' Is_Ad={is_ad}"
                    )
                    self.current_title = title
                    self.current_artist = artist
                    # No description is provided by the new logic, set to empty
                    self.current_desc = "" 
                
                # Check if current media is an advertisement
                is_currently_ad = is_ad

                # --- TIMER/AD LOGIC ---
                width = self.winfo_width() or 800
                height = self.winfo_height() or 600

                # At program start, ensure initial state is blank
                if self.timer_last_state is None:
                    # Initialize to blank state
                    self.is_ad_playing = False
                    self.timer_running = False
                    self.timer_end_time = None
                    self.timer_label.configure(text="📰 ??:??")
                    self.timer_last_state = 'blank'
                
                # Handle muting/unmuting and ad/timer display
                if is_currently_ad:
                    # If ad starts, show ad indicator, hide timer, and reset/hold timer
                    if not self.is_ad_playing:
                        l.info(f"Advertisement detected: Title='{title}' Artist='{artist}'. Muting audio.")
                        mute_all_audio(muted=True)
                        self.is_ad_playing = True
                        # Reset and hold timer
                        self.timer_running = False
                        self.timer_end_time = time.time() + 30 * 60  # Reset timer to 30:00
                        self.timer_label.configure(text="📰 ??:??")
                    # Show ad indicator
                    if self.ad_indicator_window is None:
                        self.ad_indicator_window = self.canvas.create_window(
                            width - 50, height - 30, window=self.ad_indicator, anchor="se", tags="ad_indicator"
                        )
                    # Hide timer label if visible
                    if self.timer_label_window is not None:
                        try:
                            self.canvas.delete(self.timer_label_window)
                        except Exception:
                            pass
                        self.timer_label_window = None
                    self.timer_last_state = 'ad'
                else:
                    # If ad just ended
                    if self.is_ad_playing:
                        l.info("Advertisement ended, unmuting audio and starting timer.")
                        mute_all_audio(muted=False)
                        self.is_ad_playing = False
                        # Hide ad indicator
                        if self.ad_indicator_window is not None:
                            try:
                                self.canvas.delete(self.ad_indicator_window)
                            except Exception:
                                pass
                            self.ad_indicator_window = None
                        # Start/resume timer
                        self.timer_running = True
                        # self.timer_end_time is already set to 30:00 from last ad trigger
                        self.timer_label.configure(text="30:00")
                        if self.timer_label_window is None:
                            self.timer_label_window = self.canvas.create_window(
                                width - 50, height - 30, window=self.timer_label, anchor="se", tags="timer_label"
                            )
                        self.timer_last_state = 'timer'
                    elif self.timer_running:
                        # Timer is running, update display
                        remaining = int(self.timer_end_time - time.time()) if self.timer_end_time else 0
                        if remaining > 0:
                            mins = remaining // 60
                            secs = remaining % 60
                            self.timer_label.configure(text=f"📰 {mins:02d}:{secs:02d}")
                            if self.timer_label_window is None:
                                self.timer_label_window = self.canvas.create_window(
                                    width - 50, height - 30, window=self.timer_label, anchor="se", tags="timer_label"
                                )
                            self.timer_last_state = 'timer'
                        else:
                            # Timer finished, show ??
                            l.info("Ad timer expired.")
                            self.timer_label.configure(text="📰 ??:??")
                            self.timer_running = False
                            self.timer_end_time = None
                            self.timer_last_state = 'blank'
                            if self.timer_label_window is not None:
                                try:
                                    self.canvas.delete(self.timer_label_window)
                                except Exception:
                                    pass
                            self.timer_label_window = None
                    else:
                        # Not ad, not timer running, show 📰 ??:??
                        self.timer_label.configure(text="📰 ??:??")
                        if self.timer_label_window is not None:
                            try:
                                self.canvas.delete(self.timer_label_window)
                            except Exception:
                                pass
                        self.timer_label_window = None
                        self.timer_last_state = 'blank'

            except queue.Empty:
                break # break the inner while loop if the queue is empty

        # 3. Update the labels with stored values
        self.title_label.configure(text=f"{self.current_title} — {self.current_artist}" if self.current_artist else self.current_title)
        self.desc_label.configure(text=self.current_desc or "")
        
        # Reschedule next UI update
        self.after(500, self.update_ui)

    def draw_bars(self, spectrum):
        width = self.winfo_width()    
        height = self.winfo_height()
        mid = height // 2
        bar_w = width / (BAR_COUNT * 1.5)

        if not self.bar_items:
            self._init_bars()

        for i in range(BAR_COUNT):
            val = float(self.bars[i])
            h = val * mid * 0.9
            x = i * bar_w * 1.5 + bar_w
            x1, y1, x2, y2 = x, mid - h, x + bar_w, mid
            try:
                self.canvas.coords(self.bar_items[i], x1, y1, x2, y2)
            except Exception:
                continue
            if MIRROR:
                try:
                    self.canvas.coords(self.mirror_items[i], x1, mid, x2, mid + h)
                except Exception:
                    continue
    
    @staticmethod
    def shift_color(color, shift, start_color, stop_color, max_shift=25):
        """Shift a hex color based on sine wave, bounded by start/stop colors."""
        if not GRADIENT and not DYNAMIC_GRADIENT: 
            return color
        h = color.lstrip('#')
        rgb = [int(h[i:i+2], 16) for i in (0, 2, 4)]

        # Parse start and stop colors properly
        start_h = start_color.lstrip('#')
        stop_h = stop_color.lstrip('#')
        start_rgb = [int(start_h[i:i+2], 16) for i in (0, 2, 4)]
        stop_rgb = [int(stop_h[i:i+2], 16) for i in (0, 2, 4)]

        new_rgb = []
        for j, c in enumerate(rgb):
            # Apply sine-based shift
            delta = int(max_shift * math.sin(shift + j))
            val = c + delta
            # Clamp to valid RGB range [0, 255]
            val = max(0, min(255, val))
            new_rgb.append(val)
        
        return '#{:02X}{:02X}{:02X}'.format(*new_rgb)


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
        for i in range(BAR_COUNT):
            x = i * bar_w * 1.5 + bar_w                
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
        l.debug(f"Visualizer: Re-initialized {len(self.bar_items)} bar items.")


    def _on_resize(self, event):
        """Handle canvas resize: recreate items to match new geometry."""
        l.debug(f"Canvas resized to {event.width}x{event.height}. Rebuilding bars.")
        # Recreate bar items to match new sizes; quick and infrequent (on resize only)
        self._init_bars()
        # Reposition info frame to center it horizontally
        self.canvas.coords(self.info_window, event.width // 2, 80)
        # Reposition ad indicator to bottom right
        if self.ad_indicator_window is not None and self.is_ad_playing:
            self.canvas.coords(self.ad_indicator_window, event.width - 50, event.height - 30)
        # Reposition timer label to bottom right
        if self.timer_label_window is not None and (self.timer_running or self.timer_label.cget("text") != "📰 ??:??"):
            self.canvas.coords(self.timer_label_window, event.width - 50, event.height - 30)

    def update_visuals(self):
        while not self.audio_queue.empty():
            spectrum = self.audio_queue.get()
            self.target = spectrum
            l.debug("update_visuals: new spectrum dequeued and target updated")
        self.bars = SMOOTHING * self.bars + (1 - SMOOTHING) * self.target
        self.draw_bars(self.bars)
        self.after(int(1000 / FPS), self.update_visuals)

    # Function to apply selected gradient
if __name__ == "__main__":
    # Create a temporary root window for dialogs
    try:
        root = ctk.CTk()
        root.withdraw()
        
        # The PID input dialog is removed as it's no longer necessary with the Spotify API.
        l.info("Main: Skipping PID input as Spotify API is used.")
        
        # Destroy the first root window
        root.destroy()
        
        # Ask for gradient selection if gradient is enabled
        if CONFIG.get('gradient_premaide', False) and CONFIG.get('gradient', False):
            l.info("Main: Prompting for gradient selection.")
            gradients = CONFIG.get("gradients", {})
            gradient_list = list(gradients.keys())
            if gradient_list:
                # Create a new root window for gradient selection
                from tkinter import simpledialog
                root = ctk.CTk()
                root.title("Gradient Selection")
                root.geometry("300x150")
                
                # Center window on screen
                root.update_idletasks()
                screen_width = root.winfo_screenwidth()
                screen_height = root.winfo_screenheight()
                x = (screen_width - 300) // 2
                y = (screen_height - 150) // 2
                root.geometry(f"300x150+{x}+{y}")
                
                # Create label
                label = ctk.CTkLabel(root, text="Select a gradient:", font=("Segoe UI", 14))
                label.pack(pady=10)
                
                # Create option menu
                selected_gradient = ctk.CTkOptionMenu(
                    root,
                    values=gradient_list,
                    width=200
                )
                selected_gradient.pack(pady=10)
                selected_gradient.set(gradient_list[0])  # Set default
                
                # Create confirm button
                def on_confirm():
                    root.quit()
                
                confirm_btn = ctk.CTkButton(root, text="Confirm", command=on_confirm)
                confirm_btn.pack(pady=10)
                
                root.mainloop()
                
                chosen = selected_gradient.get()
                GRADIENT_START = gradients[chosen][0]
                GRADIENT_END = gradients[chosen][1]
                l.info(f"Main: Gradient selected: {chosen} ({GRADIENT_START} -> {GRADIENT_END})")
                
                root.destroy()
    except Exception as e:
        l.debug(f"Main: Dialog setup failed: {e}")
        l.exception(f"Main: Full exception during dialog setup: {e}")

    # Two queues for inter-thread communication:
    # 1. Audio data
    # 2. Media info (title, artist, is_ad)
    audio_q = queue.Queue()
    media_q = queue.Queue()
    
    # Start audio capture thread
    audio_thread = AudioCapture(audio_q)
    # Start Spotify/Gemini media info thread
    media_thread = SpotifyMediaCapture(media_q)
    
    try:
        l.info("Main: Starting audio thread.")
        audio_thread.start()
        l.info("Main: Starting Spotify media thread.")
        media_thread.start()

        app = Visualizer(audio_q, media_q)
        l.info("Main: Starting GUI mainloop.")
        app.mainloop()
    except Exception as e:
        l.exception(f"Main: Unhandled exception: {e}")
    finally:
        l.info("Main: Stopping audio thread.")
        audio_thread.stop()
        audio_thread.join(timeout=1.0)
        
        l.info("Main: Stopping Spotify media thread.")
        media_thread.stop()
        media_thread.join(timeout=1.0)
        
        l.info("Main: Exiting application.")
