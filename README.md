# Claude Usage Widget

Floating GTK widgets for monitoring Claude.ai usage on Linux desktops.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![GTK](https://img.shields.io/badge/GTK-3.0-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

### Claude Usage Widget (`claude_usage_widget.py`)
- Displays real-time Claude.ai usage statistics
- Shows 5-hour and 7-day usage limits with progress bars
- Fetches data directly from Claude.ai API using browser cookies
- Auto-refreshes every 30 seconds

### Claude Monitor Widget (`claude_monitor_widget.py`)
- Floating terminal that embeds `claude-code-monitor` CLI
- Transparent, frameless window with VTE terminal

### Common Features
- Catppuccin-style dark theme
- Frameless, draggable windows
- System tray integration (minimize to tray)
- Always-on-top pin mode
- Transparent backgrounds

## Screenshots

*Coming soon*

## Prerequisites

- Python 3.10+
- GTK 3.0
- Linux (Ubuntu/Debian recommended)
- Chrome browser (for cookie extraction)
- Active Claude.ai Pro subscription

## Installation

### 1. Install system dependencies

```bash
# Ubuntu/Debian
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91

# For system tray support (recommended)
sudo apt install gir1.2-ayatanaappindicator3-0.1
```

### 2. Clone and setup

```bash
git clone https://github.com/anggorodewanto/claude-usage-widget.git
cd claude-usage-widget

# Run the install script (creates venv and desktop entry)
./install.sh
```

### 3. Manual setup (alternative)

```bash
# Create virtual environment
python3 -m venv venv

# Install Python dependencies
./venv/bin/pip install -r requirements.txt

# Make scripts executable
chmod +x claude_usage_widget.py claude_monitor_widget.py
```

## Usage

### Claude Usage Widget

```bash
./claude_usage_widget.py
```

**Requirements:**
- Must be logged into [claude.ai](https://claude.ai) in Chrome
- The widget extracts session cookies from Chrome automatically

### Claude Monitor Widget

```bash
./claude_monitor_widget.py
```

**Requirements:**
- [Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) CLI must be installed
- Falls back to `htop` or `top` if not available

## Controls

| Button | Action |
|--------|--------|
| Pin icon | Toggle always-on-top |
| Down arrow | Minimize to system tray |
| Refresh | Refresh data / restart monitor |
| X | Close (minimizes to tray if available) |

**Tip:** Drag anywhere on the window to move it.

## Configuration

The usage widget fetches your organization ID automatically from Claude.ai. Make sure you're logged in to Chrome with your Claude.ai account.

## Troubleshooting

### "Cookie error" or authentication failed
- Make sure you're logged into [claude.ai](https://claude.ai) in Chrome
- Try logging out and back in to Claude.ai
- Restart the widget

### No system tray icon
```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1
```

### Missing GTK dependencies
```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91
```

### Widget doesn't start
Check that Python dependencies are installed:
```bash
./venv/bin/pip install -r requirements.txt
```

## How It Works

1. **Cookie Extraction**: Uses `browser_cookie3` to extract session cookies from Chrome
2. **API Access**: Fetches usage data from Claude.ai's internal API
3. **Display**: Renders usage statistics in a GTK window with progress bars

## License

MIT License - see [LICENSE](LICENSE) for details.

## Disclaimer

This tool accesses Claude.ai's internal API using your browser cookies. It is intended for personal use to monitor your own usage. Use responsibly and in accordance with Anthropic's terms of service.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
