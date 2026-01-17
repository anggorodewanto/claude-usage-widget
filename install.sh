#!/bin/bash
# Install Claude Usage Widget to Ubuntu applications menu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/claude-usage-widget.desktop"

# Create applications directory if it doesn't exist
mkdir -p "$HOME/.local/share/applications"

# Setup venv if needed
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Setting up Python virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
    "$SCRIPT_DIR/venv/bin/pip" install browser_cookie3 cloudscraper
fi

# Update desktop file with correct path
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Claude Usage
Comment=Floating widget showing Claude.ai usage statistics
Exec=$SCRIPT_DIR/claude_usage_widget.py
Icon=utilities-system-monitor
Terminal=false
Categories=Development;Utility;
Keywords=claude;usage;monitor;
StartupWMClass=Claude Usage
EOF

# Make sure the main script is executable
chmod +x "$SCRIPT_DIR/claude_usage_widget.py"

echo "Installed! You can now:"
echo "  1. Search for 'Claude Usage' in your applications"
echo "  2. Run directly: $SCRIPT_DIR/claude_usage_widget.py"
echo ""
echo "For system tray support: sudo apt install gir1.2-ayatanaappindicator3-0.1"
echo ""
echo "To uninstall: rm $DESKTOP_FILE"
