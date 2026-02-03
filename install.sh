#!/bin/bash
# photos.local installation script

set -e

echo "=== photos.local Installation ==="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Please run without sudo. The script will request sudo when needed."
    exit 1
fi

cd /home/pi/photos

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev libopenjp2-7 libtiff5 libatlas-base-dev

# Create virtual environment
echo "Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate and install dependencies
echo "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
echo "Creating directories..."
mkdir -p config cache

# Initialize settings
if [ ! -f "config/settings.json" ]; then
    echo "Creating default settings..."
    python3 -c "import models; models.init_db()"
fi

# Install and enable systemd service
echo "Installing systemd service..."
sudo cp photos.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable photos

echo ""
echo "=== Installation Complete ==="
echo ""
echo "To start the service:"
echo "  sudo systemctl start photos"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u photos -f"
echo ""
echo "The web interface will be available at:"
echo "  http://photos.local/ or http://$(hostname -I | awk '{print $1}')/"
echo ""

# Optionally start the service
read -p "Start the service now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl start photos
    echo "Service started!"
fi
