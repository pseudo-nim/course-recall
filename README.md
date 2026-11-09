# Course Recall

A local-first Flask study app. Create courses, add notes by uploading PDF/Word/text/Markdown files or pasting text, then generate flashcards and multiple-choice questions.

## Features

- **Courses** with notes, flashcards, and quizzes stored in a local JSON file (`data/store.json`)
- **File upload**: PDF (`.pdf`), Word (`.docx`), plain text (`.txt`), Markdown (`.md`/`.markdown`)
- **Paste notes** directly into a course
- **Generation**: offline rule-based engine by default (definitions, cloze deletions, key-term MCQs); optional AI-enhanced mode using any OpenAI-compatible API
- **Study mode**: flip cards, shuffle, "needs review" filter, got-it/review tracking
- **Quiz mode**: MCQs with instant feedback on results, explanations, percentage scoring, retakes, and quiz history
- Server binds to `127.0.0.1` only — nothing is exposed beyond your machine

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000.

## AI mode (optional)

Go to **Settings**, enable *AI-enhanced generation*, and enter an OpenAI-compatible API key, base URL, and model. The key is stored only in the local JSON data file. If AI generation fails, the app falls back to the offline engine.

## Data

All data (courses, notes, cards, quizzes, settings) lives in `data/store.json`, which is gitignored. Delete that file to reset everything.
