#!/bin/bash
# Start Kid Verbal server

# Use the Python version with Flask installed
PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"

# Check if the port is already in use
if lsof -ti:5001 > /dev/null 2>&1; then
    echo "Port 5001 is already in use. Killing existing process..."
    lsof -ti:5001 | xargs kill -9 2>/dev/null
    sleep 1
fi

echo "Starting Kid Verbal on http://localhost:5001"
echo "Press Ctrl+C to stop"
echo ""

cd "$(dirname "$0")"
$PYTHON app.py
