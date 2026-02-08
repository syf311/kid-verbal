# Kid Verbal

A web app to help kids improve verbal skills through vocabulary building, gamified testing, and interactive reading sessions.

## Features

- **Multiple Profiles**: Each child has their own word list, progress, and achievements
- **Word Management**: Add words manually or from reading sessions, auto-fetch definitions
- **Four Test Types**:
  - Definition Quiz: See word, pick definition
  - Reverse Quiz: See definition, pick word
  - Spelling Bee: Hear word, type spelling
  - Fill-in-the-Blank: Complete sentences
- **Gamification**: Points, streaks, levels, badges, leaderboard
- **Adaptive Difficulty**: Questions adjust based on performance
- **Interactive Reading**: Real-time sync between parent and child devices
- **OCR Support**: Upload photos of book pages, extract text automatically

## Setup

### Prerequisites

- Python 3.11+
- Tesseract OCR (for image text extraction)

#### Install Tesseract

macOS:
```bash
brew install tesseract
```

Ubuntu/Debian:
```bash
sudo apt install tesseract-ocr
```

### Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run server (use the startup script)
./start.sh
```

Open http://localhost:5001

## Usage

1. **Create Profiles**: Add a profile for each child on the home page
2. **Add Words**: Go to "My Words" to add vocabulary words (definitions auto-fetched)
3. **Take Tests**: Choose a test type, answer questions, earn points and badges
4. **Reading Sessions**:
   - Upload reading material (image or text)
   - Open parent view on your device
   - Open child view on kid's device (same network)
   - Highlight words, ask questions, add new vocabulary

## Project Structure

```
kid-verbal/
├── app.py              # Flask server with routes and WebSocket handlers
├── database.py         # SQLite schema and connection
├── dictionary.py       # Free Dictionary API client
├── ocr.py              # Tesseract OCR wrapper
├── test_engine.py      # Test logic, scoring, badges
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates
│   ├── base.html
│   ├── home.html
│   ├── dashboard.html
│   ├── words.html
│   ├── test.html
│   ├── materials.html
│   ├── stats.html
│   ├── session_parent.html
│   └── session_child.html
├── static/             # CSS, JS, images (if needed)
├── uploads/            # Uploaded reading material images
└── verbal.db           # SQLite database (auto-created)
```

## License

MIT
