#!/bin/bash
# Start Kid Verbal server

# Use Python 3.14 (see context/coding_rules.md). The Command Line Tools Python 3.9 is built
# against LibreSSL without hashlib.scrypt, so it can't verify scrypt password hashes (login 500).
PYTHON="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"

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
