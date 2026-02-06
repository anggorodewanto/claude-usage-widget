#!/usr/bin/env python3
"""
Claude Usage Widget
A floating GTK window that displays Claude.ai usage statistics.

Requires: sudo apt install gir1.2-ayatanaappindicator3-0.1 (for tray support)
"""

import sys
import os

# Add venv packages to path for browser_cookie3 and requests
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_SITE_PACKAGES = os.path.join(SCRIPT_DIR, "venv", "lib", "python3.12", "site-packages")
if os.path.exists(VENV_SITE_PACKAGES):
    sys.path.insert(0, VENV_SITE_PACKAGES)

import gi
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, GLib, Gdk, Gio, Pango
import signal
import json
import threading
from datetime import datetime

# Import requests and browser_cookie3
try:
    import cloudscraper
    import browser_cookie3
    COOKIES_AVAILABLE = True
except ImportError as e:
    COOKIES_AVAILABLE = False
    IMPORT_ERROR = str(e)

# Try to import AppIndicator for system tray support
APP_INDICATOR_AVAILABLE = False
AppIndicator = None

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
    APP_INDICATOR_AVAILABLE = True
except (ValueError, ImportError):
    try:
        gi.require_version('AppIndicator3', '0.1')
        from gi.repository import AppIndicator3 as AppIndicator
        APP_INDICATOR_AVAILABLE = True
    except (ValueError, ImportError):
        pass


# Configuration
ORGANIZATIONS_URL = "https://claude.ai/api/organizations"
REFRESH_INTERVAL = 30  # seconds


class ClaudeUsageWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title="Claude Usage")

        # Window settings - frameless and transparent
        self.set_default_size(400, 300)
        self.set_resizable(True)
        self.set_decorated(False)
        self.set_icon_name("utilities-system-monitor")

        # Enable transparency
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Track state
        self.is_always_on_top = False
        self.is_compact_mode = False
        self.normal_size = (400, 300)
        self.indicator = None
        self.scraper = None
        self.last_data = None
        self.last_position = None
        self.org_id = None
        self.last_5h_reset = None

        # Create main container with rounded corners
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.get_style_context().add_class("main-container")
        self.add(self.main_box)

        # Create header bar with event box for dragging
        self.header = self._create_header()
        self.header_event_box = Gtk.EventBox()
        self.header_event_box.add(self.header)
        self.header_event_box.set_above_child(False)
        self.main_box.pack_start(self.header_event_box, False, False, 0)

        # Create content area
        self.content_scroll = Gtk.ScrolledWindow()
        self.content_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.content_box.set_margin_start(16)
        self.content_box.set_margin_end(16)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(12)
        self.content_scroll.add(self.content_box)
        self.main_box.pack_start(self.content_scroll, True, True, 0)

        # Create status bar
        self.status_bar = self._create_status_bar()
        self.main_box.pack_start(self.status_bar, False, False, 0)

        # Connect signals
        self.connect("delete-event", self.on_delete_event)

        # Enable window dragging from anywhere
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.on_window_press)

        # Setup system tray
        if APP_INDICATOR_AVAILABLE:
            self._setup_system_tray()

        # Initial content
        self._show_loading()

        # Load cookies and start fetching
        if COOKIES_AVAILABLE:
            self._load_cookies()
        else:
            self._show_error(f"Missing dependencies: {IMPORT_ERROR}\n\nRun: cd {SCRIPT_DIR} && python3 -m venv venv && ./venv/bin/pip install browser_cookie3 cloudscraper")

    def _create_header(self):
        """Create the header bar with controls."""
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_margin_start(8)
        header.set_margin_end(8)
        header.set_margin_top(4)
        header.set_margin_bottom(4)
        header.get_style_context().add_class("header-box")

        # Title label (shown in normal mode)
        self.title_label = Gtk.Label(label="Claude Usage")
        self.title_label.get_style_context().add_class("title-label")
        header.pack_start(self.title_label, False, False, 0)

        # Usage summary label (shown in compact mode)
        self.usage_summary_label = Gtk.Label(label="")
        self.usage_summary_label.get_style_context().add_class("usage-summary")
        self.usage_summary_label.set_no_show_all(True)
        header.pack_start(self.usage_summary_label, False, False, 0)

        # Spacer
        header.pack_start(Gtk.Box(), True, True, 0)

        # Always on top button
        self.pin_btn = Gtk.ToggleButton()
        self.pin_btn.set_tooltip_text("Always on top")
        pin_icon = Gtk.Image.new_from_icon_name("view-pin-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.pin_btn.add(pin_icon)
        self.pin_btn.connect("toggled", self.on_toggle_always_on_top)
        header.pack_start(self.pin_btn, False, False, 0)

        # Compact mode toggle button
        self.compact_btn = Gtk.ToggleButton()
        self.compact_btn.set_tooltip_text("Toggle compact mode")
        compact_icon = Gtk.Image.new_from_icon_name("view-compact-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.compact_btn.add(compact_icon)
        self.compact_btn.connect("toggled", self.on_toggle_compact_mode)
        header.pack_start(self.compact_btn, False, False, 0)

        # Refresh button
        refresh_btn = Gtk.Button()
        refresh_btn.set_tooltip_text("Refresh now")
        refresh_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        refresh_btn.add(refresh_icon)
        refresh_btn.connect("clicked", lambda b: self._fetch_usage())
        header.pack_start(refresh_btn, False, False, 0)

        # Close button
        close_btn = Gtk.Button()
        close_btn.set_tooltip_text("Close")
        close_btn.get_style_context().add_class("close-button")
        close_icon = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        close_btn.add(close_icon)
        close_btn.connect("clicked", self.on_close_clicked)
        header.pack_start(close_btn, False, False, 0)

        return header

    def _create_status_bar(self):
        """Create status bar."""
        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status.set_margin_start(8)
        status.set_margin_end(8)
        status.set_margin_top(2)
        status.set_margin_bottom(2)

        self.status_label = Gtk.Label(label="Loading...")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.get_style_context().add_class("status-label")
        status.pack_start(self.status_label, True, True, 0)

        return status

    def _setup_system_tray(self):
        """Setup system tray indicator."""
        self.indicator = AppIndicator.Indicator.new(
            "claude-usage",
            "utilities-system-monitor",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Claude Usage")

        menu = Gtk.Menu()

        self.show_item = Gtk.MenuItem(label="Show Window")
        self.show_item.connect("activate", self.on_tray_show)
        menu.append(self.show_item)

        refresh_item = Gtk.MenuItem(label="Refresh")
        refresh_item.connect("activate", lambda w: self._fetch_usage())
        menu.append(refresh_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_tray_quit)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def _load_cookies(self):
        """Load cookies from Chrome and setup scraper."""
        try:
            cookies = browser_cookie3.chrome(domain_name=".claude.ai")
            self.cookie_dict = {c.name: c.value for c in cookies}

            # Create cloudscraper session
            self.scraper = cloudscraper.create_scraper()
            for name, value in self.cookie_dict.items():
                self.scraper.cookies.set(name, value, domain=".claude.ai")

            self.status_label.set_text("Cookies loaded, fetching org...")
            self._fetch_organization()
        except Exception as e:
            self.status_label.set_text(f"Cookie error: {e}")
            self.scraper = None

    def _fetch_organization(self):
        """Fetch organization ID from Claude.ai API."""
        def fetch():
            try:
                response = self.scraper.get(ORGANIZATIONS_URL, timeout=10)
                if response.status_code == 200:
                    orgs = response.json()
                    if orgs and len(orgs) > 0:
                        self.org_id = orgs[0].get("uuid")
                        GLib.idle_add(self._on_org_fetched)
                    else:
                        GLib.idle_add(self._show_error, "No organizations found")
                else:
                    GLib.idle_add(self._show_error, f"Failed to fetch organizations: HTTP {response.status_code}")
            except Exception as e:
                GLib.idle_add(self._show_error, f"Failed to fetch organization: {e}")

        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()

    def _on_org_fetched(self):
        """Called when organization ID is fetched successfully."""
        self.status_label.set_text(f"Organization loaded")
        self._fetch_usage()
        # Setup periodic refresh
        GLib.timeout_add_seconds(REFRESH_INTERVAL, self._fetch_usage)

    def _fetch_usage(self):
        """Fetch usage data in background thread."""
        if not self.scraper:
            self._show_error("No cookies available. Make sure you're logged into claude.ai in Chrome.")
            return True

        if not self.org_id:
            self._show_error("No organization ID. Please restart the widget.")
            return True

        usage_url = f"https://claude.ai/api/organizations/{self.org_id}/usage"

        def fetch():
            try:
                response = self.scraper.get(usage_url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    GLib.idle_add(self._update_display, data)
                elif response.status_code == 401:
                    GLib.idle_add(self._show_error, "Authentication failed. Please log into claude.ai in Chrome and restart.")
                else:
                    GLib.idle_add(self._show_error, f"HTTP {response.status_code}: {response.text[:200]}")
            except Exception as e:
                print(f"Fetch error: {e}")
                GLib.idle_add(self._show_error, str(e))

        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()
        return True  # Continue periodic refresh

    def _clear_content(self):
        """Clear content box."""
        for child in self.content_box.get_children():
            self.content_box.remove(child)

    def _show_loading(self):
        """Show loading message."""
        self._clear_content()
        label = Gtk.Label(label="Loading...")
        label.get_style_context().add_class("content-text")
        self.content_box.pack_start(label, True, True, 0)
        self.content_box.show_all()

    def _show_error(self, message):
        """Show error message."""
        print(f"Error: {message}")
        self._clear_content()
        label = Gtk.Label(label=f"Error: {message}")
        label.set_line_wrap(True)
        label.set_max_width_chars(40)
        label.get_style_context().add_class("error-text")
        self.content_box.pack_start(label, True, True, 0)
        self.content_box.show_all()
        self.status_label.set_text("Error")
        
        # Also update tray label to indicate error
        if self.indicator:
            self.indicator.set_label("⚠️ Error", "Claude Usage")

    def _update_display(self, data):
        """Update the display with usage data."""
        self._clear_content()
        
        # Check for 5-hour reset
        if data and isinstance(data, dict) and "five_hour" in data:
            current_reset = data["five_hour"].get("resets_at")
            if self.last_5h_reset and current_reset != self.last_5h_reset:
                self._send_reset_prompt()
            self.last_5h_reset = current_reset
        
        self.last_data = data

        try:
            # Handle the usage data structure
            # The structure may vary - let's handle common formats
            if isinstance(data, dict):
                self._render_usage_data(data)
            else:
                # Fallback: show raw JSON
                label = Gtk.Label(label=json.dumps(data, indent=2))
                label.set_selectable(True)
                label.get_style_context().add_class("content-text")
                self.content_box.pack_start(label, False, False, 0)

            now = datetime.now().strftime("%H:%M:%S")
            self.status_label.set_text(f"Updated: {now} | Refresh: {REFRESH_INTERVAL}s")

        except Exception as e:
            print(f"Update error: {e}")
            self._show_error(f"Parse error: {e}")

        # Always update usage summary (it also updates tray label)
        # We do this outside the try/except to ensure tray reflects something
        self._update_usage_summary()
        self.content_box.show_all()

    def _parse_reset_time(self, reset_str):
        """Parse reset time and return human-readable string."""
        from datetime import datetime, timezone
        try:
            reset_dt = datetime.fromisoformat(reset_str.replace('+00:00', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = reset_dt - now
            hours = int(diff.total_seconds() // 3600)
            minutes = int((diff.total_seconds() % 3600) // 60)
            if hours > 0:
                return f"{hours}h{minutes}m"
            return f"{minutes}m"
        except:
            return "unknown"

    def _render_usage_data(self, data):
        """Render Claude.ai usage data."""
        # 5-hour usage (primary rate limit)
        if "five_hour" in data and data["five_hour"]:
            usage = data["five_hour"]
            util = usage.get("utilization", 0)
            reset = self._parse_reset_time(usage.get("resets_at", ""))
            self._add_usage_bar("5-Hour Usage", util, 100, f"Resets in {reset}")

        # 7-day usage (overall limit)
        if "seven_day" in data and data["seven_day"]:
            usage = data["seven_day"]
            util = usage.get("utilization", 0)
            reset = self._parse_reset_time(usage.get("resets_at", ""))
            self._add_usage_bar("7-Day Usage", util, 100, f"Resets in {reset}")

        # 7-day Opus usage
        if "seven_day_opus" in data and data["seven_day_opus"]:
            usage = data["seven_day_opus"]
            util = usage.get("utilization", 0)
            reset = self._parse_reset_time(usage.get("resets_at", ""))
            self._add_usage_bar("Opus (7-Day)", util, 100, f"Resets in {reset}")

        # 7-day Sonnet usage
        if "seven_day_sonnet" in data and data["seven_day_sonnet"]:
            usage = data["seven_day_sonnet"]
            util = usage.get("utilization", 0)
            reset = self._parse_reset_time(usage.get("resets_at", ""))
            self._add_usage_bar("Sonnet (7-Day)", util, 100, f"Resets in {reset}")

        # Extra usage if available
        if "extra_usage" in data and data["extra_usage"]:
            self._add_section("Extra Usage", data["extra_usage"])

    def _add_section(self, title, data):
        """Add a section with title and data."""
        # Section title
        title_label = Gtk.Label()
        title_label.set_markup(f"<b>{title}</b>")
        title_label.set_halign(Gtk.Align.START)
        title_label.get_style_context().add_class("section-title")
        self.content_box.pack_start(title_label, False, False, 0)

        # Section content
        if isinstance(data, dict):
            for key, value in data.items():
                self._add_field(key, value)
        else:
            self._add_field(None, data)

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(8)
        sep.set_margin_bottom(8)
        self.content_box.pack_start(sep, False, False, 0)

    def _add_field(self, key, value):
        """Add a key-value field."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        if key:
            # Format key nicely
            display_key = key.replace("_", " ").title()
            key_label = Gtk.Label(label=f"{display_key}:")
            key_label.set_halign(Gtk.Align.START)
            key_label.get_style_context().add_class("field-key")
            box.pack_start(key_label, False, False, 0)

        # Format value
        if isinstance(value, (dict, list)):
            display_value = json.dumps(value, indent=2)
        else:
            display_value = str(value)

        value_label = Gtk.Label(label=display_value)
        value_label.set_halign(Gtk.Align.END if key else Gtk.Align.START)
        value_label.set_selectable(True)
        value_label.get_style_context().add_class("field-value")
        box.pack_end(value_label, False, False, 0)

        self.content_box.pack_start(box, False, False, 2)

    def _add_usage_bar(self, label, used, limit, subtitle=None):
        """Add a usage progress bar."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Header with label and percentage
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        name_label = Gtk.Label(label=label)
        name_label.set_halign(Gtk.Align.START)
        name_label.get_style_context().add_class("field-key")
        header.pack_start(name_label, False, False, 0)

        pct_label = Gtk.Label(label=f"{used:.0f}%")
        pct_label.set_halign(Gtk.Align.END)
        pct_label.get_style_context().add_class("field-value")
        header.pack_end(pct_label, False, False, 0)

        box.pack_start(header, False, False, 0)

        # Progress bar
        progress = Gtk.ProgressBar()
        fraction = min(1.0, used / limit) if limit > 0 else 0
        progress.set_fraction(fraction)
        if fraction > 0.9:
            progress.get_style_context().add_class("usage-critical")
        elif fraction > 0.7:
            progress.get_style_context().add_class("usage-warning")
        box.pack_start(progress, False, False, 0)

        # Subtitle (reset time)
        if subtitle:
            sub_label = Gtk.Label(label=subtitle)
            sub_label.set_halign(Gtk.Align.START)
            sub_label.get_style_context().add_class("status-label")
            box.pack_start(sub_label, False, False, 0)

        self.content_box.pack_start(box, False, False, 8)

    def _send_reset_prompt(self):
        """Send a small prompt to Claude when 5-hour window resets."""
        def send():
            try:
                # Create new conversation
                conv_response = self.scraper.post(
                    f"https://claude.ai/api/organizations/{self.org_id}/chat_conversations",
                    json={"name": ""}, timeout=10
                )
                if conv_response.status_code != 201:
                    print(f"Failed to create conversation: {conv_response.status_code}")
                    return
                
                conv_uuid = conv_response.json().get("uuid")
                
                # Send minimal prompt
                self.scraper.post(
                    f"https://claude.ai/api/organizations/{self.org_id}/chat_conversations/{conv_uuid}/completion",
                    json={"prompt": "hi", "timezone": "UTC", "model": "claude-3-5-sonnet-20241022", "attachments": []},
                    timeout=30, stream=True
                )
                print("Reset prompt sent successfully")
                
            except Exception as e:
                print(f"Failed to send reset prompt: {e}")
        
        threading.Thread(target=send, daemon=True).start()

    def on_toggle_always_on_top(self, button):
        """Toggle always-on-top mode."""
        self.is_always_on_top = button.get_active()
        self.set_keep_above(self.is_always_on_top)

    def on_toggle_compact_mode(self, button):
        """Toggle compact mode - show only header with usage text."""
        self.is_compact_mode = button.get_active()
        if self.is_compact_mode:
            # Save current size before going compact
            self.normal_size = self.get_size()
            # Hide content and status bar
            self.content_scroll.hide()
            self.status_bar.hide()
            # Show usage summary in header, hide title
            self.title_label.hide()
            self.usage_summary_label.show()
            self._update_usage_summary()
            # Add compact mode class to header for smaller buttons
            self.header.get_style_context().add_class("compact-mode")
            # Resize to fit header only
            self.resize(1, 1)  # Let GTK calculate minimum size
        else:
            # Show content and status bar
            self.content_scroll.show()
            self.status_bar.show()
            # Hide usage summary, show title
            self.usage_summary_label.hide()
            self.title_label.show()
            # Remove compact mode class from header
            self.header.get_style_context().remove_class("compact-mode")
            # Restore previous size
            self.resize(*self.normal_size)

    def _update_usage_summary(self):
        """Update the compact usage summary text and tray label."""
        if not self.last_data:
            summary = "Loading..."
            self.usage_summary_label.set_text(summary)
            if self.indicator:
                self.indicator.set_label(summary, "Claude Usage")
            return

        parts = []
        try:
            if "five_hour" in self.last_data and self.last_data["five_hour"]:
                usage = self.last_data["five_hour"]
                util = usage.get("utilization", 0)
                # Ensure util is numeric
                try: util = float(util)
                except: util = 0
                reset = self._parse_reset_time(usage.get("resets_at", ""))
                parts.append(f"5h: {util:.0f}% ({reset})")
            if "seven_day" in self.last_data and self.last_data["seven_day"]:
                usage = self.last_data["seven_day"]
                util = usage.get("utilization", 0)
                # Ensure util is numeric
                try: util = float(util)
                except: util = 0
                parts.append(f"7d: {util:.0f}%")
        except Exception as e:
            print(f"Summary update error: {e}")

        summary = " | ".join(parts) if parts else "No data"
        self.usage_summary_label.set_text(summary)
        
        # Also update tray label
        if self.indicator:
            self.indicator.set_label(summary, "Claude Usage")

    def on_window_press(self, widget, event):
        """Start window drag using GTK's native method."""
        if event.button == 1:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
        return False

    def on_close_clicked(self, button):
        """Handle close button click."""
        self.on_delete_event(self, None)

    def on_minimize_to_tray(self, button):
        """Minimize window to system tray."""
        self.last_position = self.get_position()
        self.hide()
        if self.indicator:
            self.show_item.set_label("Show Window")

    def on_tray_show(self, widget):
        """Show/hide window from tray menu."""
        if self.is_visible():
            self.last_position = self.get_position()
            self.hide()
            self.show_item.set_label("Show Window")
        else:
            if self.last_position:
                self.move(*self.last_position)
            self.show()
            self.present()
            if self.is_always_on_top:
                self.set_keep_above(True)
            self.show_item.set_label("Hide Window")

    def on_tray_quit(self, widget):
        """Quit from tray menu."""
        Gtk.main_quit()

    def on_delete_event(self, widget, event):
        """Handle window close."""
        if APP_INDICATOR_AVAILABLE:
            self.last_position = self.get_position()
            self.hide()
            if self.indicator:
                self.show_item.set_label("Show Window")
            return True
        else:
            Gtk.main_quit()
            return False


def apply_css():
    """Apply custom CSS styling."""
    css = b"""
    window {
        background-color: transparent;
    }

    .main-container {
        background-color: rgba(30, 30, 46, 0.92);
        border-radius: 12px;
        border: 1px solid rgba(69, 71, 90, 0.6);
        margin: 4px;
    }

    .header-box {
        background-color: rgba(49, 50, 68, 0.8);
        border-radius: 10px 10px 0 0;
        padding: 6px;
    }

    .title-label {
        color: #cdd6f4;
        font-weight: bold;
        font-size: 11px;
        opacity: 0.9;
    }

    .usage-summary {
        color: #a6e3a1;
        font-weight: bold;
        font-size: 11px;
    }

    .status-label {
        color: #a6adc8;
        font-size: 9px;
        opacity: 0.8;
    }

    .section-title {
        color: #89b4fa;
        font-size: 13px;
        margin-top: 8px;
    }

    .field-key {
        color: #a6adc8;
        font-size: 11px;
    }

    .field-value {
        color: #cdd6f4;
        font-size: 11px;
    }

    .content-text {
        color: #cdd6f4;
        font-family: monospace;
        font-size: 10px;
    }

    .error-text {
        color: #f38ba8;
        font-size: 11px;
    }

    button {
        background: rgba(69, 71, 90, 0.6);
        border: none;
        border-radius: 6px;
        padding: 4px 8px;
        color: #cdd6f4;
        min-width: 24px;
        min-height: 24px;
    }

    button:hover {
        background: rgba(88, 91, 112, 0.8);
    }

    button:checked {
        background: rgba(137, 180, 250, 0.9);
        color: #1e1e2e;
    }

    .compact-mode button {
        min-width: 18px;
        min-height: 18px;
        padding: 2px 4px;
        border-radius: 4px;
    }

    .close-button {
        background: rgba(243, 139, 168, 0.3);
    }

    .close-button:hover {
        background: rgba(243, 139, 168, 0.7);
    }

    scrolledwindow {
        border: none;
        background: transparent;
    }

    scrollbar {
        background: transparent;
    }

    scrollbar slider {
        background: rgba(88, 91, 112, 0.5);
        border-radius: 4px;
        min-width: 6px;
    }

    scrollbar slider:hover {
        background: rgba(88, 91, 112, 0.8);
    }

    progressbar trough {
        background-color: rgba(69, 71, 90, 0.5);
        border-radius: 4px;
        min-height: 6px;
    }

    progressbar progress {
        background-color: rgba(166, 227, 161, 0.9);
        border-radius: 4px;
    }

    progressbar.usage-warning progress {
        background-color: rgba(249, 226, 175, 0.9);
    }

    progressbar.usage-critical progress {
        background-color: rgba(243, 139, 168, 0.9);
    }

    separator {
        background-color: rgba(69, 71, 90, 0.4);
        min-height: 1px;
    }
    """

    provider = Gtk.CssProvider()
    provider.load_from_data(css)

    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    apply_css()

    window = ClaudeUsageWidget()
    window.show_all()

    Gtk.main()


if __name__ == "__main__":
    main()
