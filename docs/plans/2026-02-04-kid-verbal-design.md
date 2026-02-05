# Kid Verbal - Design Document

A web app to help kids improve verbal skills through vocabulary building, testing, and interactive reading sessions.

## Overview

**Goals:**
- Build vocabulary through word lists with definitions
- Test understanding via multiple quiz types
- Practice spelling through audio-based challenges
- Interactive reading sessions with parent monitoring and engagement

**Tech Stack:**
- Python backend (Flask or FastAPI)
- SQLite database
- Vanilla HTML/CSS/JavaScript frontend
- WebSocket for real-time reading session sync
- Tesseract OCR for image text extraction
- Free Dictionary API for definitions
- Browser TTS for pronunciation

## Users & Access

- Multiple child profiles, each with separate word lists and progress
- Local network access only (same network, different devices)
- No authentication - trusted local environment, pick profile from list

## Architecture

```
kid-verbal/
├── app.py              # Main server
├── database.py         # SQLite models and queries
├── ocr.py              # Image text extraction
├── dictionary.py       # Dictionary API client
├── static/             # CSS, JS, images
├── templates/          # HTML templates
├── uploads/            # Reading material images
└── verbal.db           # SQLite database
```

## Database Schema

### Child
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Child's name |
| avatar | TEXT | Optional avatar identifier |
| created_at | DATETIME | Profile creation time |

### Word
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| child_id | INTEGER FK | Owner child |
| word | TEXT | The vocabulary word |
| definition | TEXT | Word definition |
| example_sentence | TEXT | Optional usage example |
| created_at | DATETIME | When added |

### WordProgress
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| child_id | INTEGER FK | Child being tested |
| word_id | INTEGER FK | Word being tested |
| correct_count | INTEGER | Total correct answers |
| wrong_count | INTEGER | Total wrong answers |
| streak | INTEGER | Current consecutive correct |
| difficulty_level | INTEGER | 1-5, affects frequency and timing |
| last_tested | DATETIME | Last test time |

### ReadingMaterial
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| title | TEXT | Material title |
| content | TEXT | Extracted/entered text |
| image_path | TEXT | Optional source image path |
| created_at | DATETIME | Upload time |

### TestSession
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| child_id | INTEGER FK | Child who took test |
| test_type | TEXT | Quiz type identifier |
| score | INTEGER | Points earned |
| correct_count | INTEGER | Correct answers |
| total_count | INTEGER | Total questions |
| time_taken | INTEGER | Seconds elapsed |
| created_at | DATETIME | Session time |

### Badge
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| child_id | INTEGER FK | Badge owner |
| badge_type | TEXT | Badge identifier |
| earned_at | DATETIME | When earned |

## Features

### Word Management

**Adding Words:**
- Manual entry: type word, auto-fetch definition from Free Dictionary API
- Edit fetched definition, add example sentence
- From reading session: highlight word → confirm → adds to child's list

**Word List View:**
- See all words with definitions
- Edit or delete words
- Visual indicator of mastery level (based on WordProgress)

### Testing System

**Test Types:**

1. **Definition Quiz**
   - Show word, pick correct definition from 4 choices
   - 3 wrong choices pulled from other words in child's list
   - Timer: starts at 15 seconds, adjusts by difficulty

2. **Reverse Quiz**
   - Show definition, pick the correct word from 4 choices
   - Same mechanics as definition quiz

3. **Spelling Bee**
   - TTS speaks the word
   - Child types the spelling
   - Option to hear again, see definition as hint
   - Timer: 20 seconds base, adjusts by difficulty

4. **Fill-in-the-Blank**
   - Show example sentence with word blanked out
   - Child types or picks the word
   - Requires words to have example sentences

**Gamification:**

| Element | Mechanic |
|---------|----------|
| Points | +10 correct, +5 streak bonus, +15 hard word bonus |
| Streaks | Consecutive correct, resets on wrong |
| Levels | Every 100 points = level up |
| Leaderboard | Compare total points/levels between children |

**Badges:**
- "First Steps" - Add first 10 words
- "Scholar" - Add 50 words
- "Sharp Mind" - 10 correct in a row
- "Unstoppable" - 25 correct in a row
- "Speed Demon" - Average < 3 seconds for 10 questions
- "Dedicated" - 7-day testing streak
- "Master" - Get a word to difficulty level 5

**Adaptive Difficulty:**
- Words start at difficulty level 1
- Correct → difficulty increases (asked less often, shorter timer)
- Wrong → difficulty decreases (asked more often, longer timer)
- Test word selection weighted toward lower difficulty (struggling) words

### Interactive Reading Sessions

**Creating Material:**
1. Upload image (photo of book page) OR paste text directly
2. OCR extracts text from image (Tesseract)
3. Edit/correct extracted text
4. Save with title

**Session Participants:**
- Parent opens `/session/<id>/parent`
- Child opens `/session/<id>/child`
- Connected via WebSocket on local network

**Parent View:**
- Full text displayed
- Click any word to highlight it (syncs to child)
- Buttons: "What does this mean?" / "Add to word list"
- Quick question input: type question, optional multiple choice
- Reading progress indicator (child's scroll position)

**Child View:**
- Same text, highlighted words appear in real-time
- Question popup when parent asks
- Respond verbally (parent judges) or tap choices
- "I don't know" button for highlighted words

**WebSocket Events:**
| Event | Direction | Payload |
|-------|-----------|---------|
| highlight_word | Parent → Child | word, position |
| clear_highlight | Parent → Child | - |
| ask_question | Parent → Child | question, choices (optional) |
| child_response | Child → Parent | response type, answer |
| scroll_position | Child → Parent | scroll percentage |
| add_to_words | Parent → Server | word, child_id |

## UI Pages

| Route | Purpose |
|-------|---------|
| `/` | Home - pick child profile or create new |
| `/child/<id>` | Dashboard - stats, recent activity, start test |
| `/child/<id>/words` | Word list - view, add, edit, delete |
| `/child/<id>/test` | Test mode - pick type, configure, start |
| `/child/<id>/stats` | Progress charts, badges, leaderboard |
| `/materials` | Reading materials list, upload new |
| `/session/<id>/parent` | Parent view of reading session |
| `/session/<id>/child` | Child view of reading session |

## UI Design Principles

- **Mobile-friendly:** Responsive, works on tablets
- **Large targets:** Big buttons for young children
- **Simple navigation:** Minimal text, icon-based where possible
- **Bright colors:** Friendly, engaging palette
- **Visual feedback:** Progress bars, animations
- **Celebrations:** Confetti on level up, badge animations

## External Dependencies

- **pytesseract + Tesseract OCR:** Image text extraction
- **Free Dictionary API:** Word definitions (https://dictionaryapi.dev/)
- **Browser Web Speech API:** Text-to-speech for pronunciation
- **Flask-SocketIO or FastAPI WebSockets:** Real-time sync

## Future Considerations (Not in Initial Scope)

- Word categories/tags for organization
- Custom audio recordings for words
- Speech recognition for verbal responses
- Export/import word lists
- Multiple language support
