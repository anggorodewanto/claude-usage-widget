#!/usr/bin/env python3
"""
Claude Code Monitor Widget
A floating GTK window that runs claude-code-monitor with taskbar integration.

System tray requires: sudo apt install gir1.2-ayatanaappindicator3-0.1
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from gi.repository import Gtk, Vte, GLib, Gdk, Gio
import os
import signal

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


class ClaudeMonitorWidget(Gtk.Window):
    def __init__(self):
        super().__init__(title="Claude Monitor")

        # Window settings - frameless and transparent
        self.set_default_size(800, 600)
        self.set_resizable(True)
        self.set_decorated(False)
        self.set_icon_name("utilities-terminal")

        # Enable transparency
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Track state
        self.is_always_on_top = False
        self.is_compact = False
        self.normal_size = (800, 600)
        self.indicator = None
        self.last_position = None

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

        # Create terminal
        self.terminal = self._create_terminal()

        # Scrolled window for terminal
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.add(self.terminal)
        self.main_box.pack_start(self.scrolled, True, True, 0)

        # Create status bar
        self.status_bar = self._create_status_bar()
        self.main_box.pack_start(self.status_bar, False, False, 0)

        # Connect signals
        self.connect("delete-event", self.on_delete_event)
        self.connect("configure-event", self.on_configure)

        # Enable window dragging from anywhere
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.on_window_press)

        # Setup system tray
        if APP_INDICATOR_AVAILABLE:
            self._setup_system_tray()

        # Start the monitor
        self.spawn_monitor()

    def _create_header(self):
        """Create the header bar with controls."""
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_margin_start(8)
        header.set_margin_end(8)
        header.set_margin_top(4)
        header.set_margin_bottom(4)

        # Apply dark background
        header.get_style_context().add_class("header-box")

        # Title label
        title = Gtk.Label(label="Claude Monitor")
        title.get_style_context().add_class("title-label")
        header.pack_start(title, False, False, 0)

        # Spacer
        header.pack_start(Gtk.Box(), True, True, 0)

        # Always on top button
        self.pin_btn = Gtk.ToggleButton()
        self.pin_btn.set_tooltip_text("Always on top")
        pin_icon = Gtk.Image.new_from_icon_name("view-pin-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.pin_btn.add(pin_icon)
        self.pin_btn.connect("toggled", self.on_toggle_always_on_top)
        header.pack_start(self.pin_btn, False, False, 0)

        # Compact mode button
        self.compact_btn = Gtk.ToggleButton()
        self.compact_btn.set_tooltip_text("Compact mode")
        compact_icon = Gtk.Image.new_from_icon_name("view-compact-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.compact_btn.add(compact_icon)
        self.compact_btn.connect("toggled", self.on_toggle_compact)
        header.pack_start(self.compact_btn, False, False, 0)

        # Minimize to tray button (only if tray is available)
        if APP_INDICATOR_AVAILABLE:
            tray_btn = Gtk.Button()
            tray_btn.set_tooltip_text("Minimize to tray")
            tray_icon = Gtk.Image.new_from_icon_name("go-down-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
            tray_btn.add(tray_icon)
            tray_btn.connect("clicked", self.on_minimize_to_tray)
            header.pack_start(tray_btn, False, False, 0)

        # Restart button
        restart_btn = Gtk.Button()
        restart_btn.set_tooltip_text("Restart monitor")
        restart_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        restart_btn.add(restart_icon)
        restart_btn.connect("clicked", self.on_restart)
        header.pack_start(restart_btn, False, False, 0)

        # Close button
        close_btn = Gtk.Button()
        close_btn.set_tooltip_text("Close")
        close_btn.get_style_context().add_class("close-button")
        close_icon = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        close_btn.add(close_icon)
        close_btn.connect("clicked", self.on_close_clicked)
        header.pack_start(close_btn, False, False, 0)

        return header

    def _create_terminal(self):
        """Create and configure the VTE terminal."""
        terminal = Vte.Terminal()

        # Terminal settings
        terminal.set_scrollback_lines(10000)
        terminal.set_scroll_on_output(True)
        terminal.set_scroll_on_keystroke(True)

        # Set dark theme colors with transparency
        bg_color = Gdk.RGBA()
        bg_color.red = 0.118
        bg_color.green = 0.118
        bg_color.blue = 0.18
        bg_color.alpha = 0.85
        fg_color = Gdk.RGBA()
        fg_color.parse("#cdd6f4")

        terminal.set_color_background(bg_color)
        terminal.set_color_foreground(fg_color)

        # Cursor color
        cursor_color = Gdk.RGBA()
        cursor_color.parse("#f5e0dc")
        terminal.set_color_cursor(cursor_color)

        # Connect child exit signal
        terminal.connect("child-exited", self.on_child_exited)

        return terminal

    def _create_status_bar(self):
        """Create status bar."""
        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status.set_margin_start(8)
        status.set_margin_end(8)
        status.set_margin_top(2)
        status.set_margin_bottom(2)

        self.status_label = Gtk.Label(label="Running...")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.get_style_context().add_class("status-label")
        status.pack_start(self.status_label, True, True, 0)

        # Show tray status
        if not APP_INDICATOR_AVAILABLE:
            tray_hint = Gtk.Label(label="(Install gir1.2-ayatanaappindicator3-0.1 for tray support)")
            tray_hint.get_style_context().add_class("status-label")
            status.pack_end(tray_hint, False, False, 0)

        return status

    def _setup_system_tray(self):
        """Setup system tray indicator."""
        self.indicator = AppIndicator.Indicator.new(
            "claude-monitor",
            "utilities-terminal",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Claude Monitor")

        # Create tray menu
        menu = Gtk.Menu()

        # Show/Hide item
        self.show_item = Gtk.MenuItem(label="Show Window")
        self.show_item.connect("activate", self.on_tray_show)
        menu.append(self.show_item)

        # Restart item
        restart_item = Gtk.MenuItem(label="Restart Monitor")
        restart_item.connect("activate", lambda w: self.on_restart(None))
        menu.append(restart_item)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Quit item
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_tray_quit)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def spawn_monitor(self):
        """Spawn the claude-code-monitor process in the terminal."""
        shell = os.environ.get("SHELL", "/bin/bash")

        # Command with --plan max5 flag
        command = [
            shell, "-c",
            "command -v claude-code-monitor >/dev/null 2>&1 && claude-code-monitor --plan max5 || "
            "(echo 'claude-code-monitor not found.'; echo 'Install it or edit the command in this script.'; "
            "echo ''; echo 'For now, showing a demo with htop or top:'; echo ''; "
            "command -v htop >/dev/null 2>&1 && htop || top)"
        ]

        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.environ.get("HOME"),
            command,
            None,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            self.on_spawn_callback,
            None
        )

    def on_spawn_callback(self, terminal, pid, error, user_data):
        """Callback after spawn completes."""
        if error:
            self.status_label.set_text(f"Error: {error.message}")
        else:
            self.child_pid = pid
            self.status_label.set_text(f"Running (PID: {pid})")

    def on_child_exited(self, terminal, status):
        """Handle child process exit."""
        self.status_label.set_text(f"Process exited (code: {status})")

    def on_toggle_always_on_top(self, button):
        """Toggle always-on-top mode."""
        self.is_always_on_top = button.get_active()
        self.set_keep_above(self.is_always_on_top)

    def on_toggle_compact(self, button):
        """Toggle compact mode."""
        self.is_compact = button.get_active()
        if self.is_compact:
            self.normal_size = self.get_size()
            self.resize(400, 250)
            self.header.hide()
            self.status_bar.hide()
        else:
            self.header.show()
            self.status_bar.show()
            self.resize(*self.normal_size)

    def on_configure(self, widget, event):
        """Handle window resize/move."""
        if not self.is_compact:
            self.normal_size = (event.width, event.height)
        return False

    def on_window_press(self, widget, event):
        """Start window drag using GTK's native method."""
        if event.button == 1:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
        return False

    def on_close_clicked(self, button):
        """Handle close button click."""
        self.on_delete_event(self, None)

    def on_restart(self, button):
        """Restart the monitor process."""
        self.terminal.reset(True, True)
        self.spawn_monitor()
        self.status_label.set_text("Restarting...")

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
        """Handle window close - minimize to tray if available, otherwise quit."""
        if APP_INDICATOR_AVAILABLE:
            self.last_position = self.get_position()
            self.hide()
            if self.indicator:
                self.show_item.set_label("Show Window")
            return True  # Prevent destruction
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

    .status-label {
        color: #a6adc8;
        font-size: 9px;
        opacity: 0.8;
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
    """

    provider = Gtk.CssProvider()
    provider.load_from_data(css)

    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def main():
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Apply CSS
    apply_css()

    # Create and show window
    window = ClaudeMonitorWidget()
    window.show_all()

    # Run main loop
    Gtk.main()


if __name__ == "__main__":
    main()
