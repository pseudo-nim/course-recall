"""Course Recall - local-first Flask study app."""
import os
import time

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

import extractors
import generator
import storage

app = Flask(__name__)
app.secret_key = "course-recall-local-key"

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
MAX_CONTENT_LENGTH = 20 * 1024 * 1024
ALLOWED_NOTE_SOURCES = ["file", "paste"]


@app.context_processor
def inject_settings():
    return {"ai_enabled": storage.get_settings().get("ai_enabled", False)}


@app.route("/")
def index():
    store = storage.load()
    courses = sorted(store["courses"].values(), key=lambda c: c.get("created_at", ""), reverse=True)
    return render_template("index.html", courses=courses)


@app.route("/courses/create", methods=["POST"])
def create_course():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Course name is required.")
        return redirect(url_for("index"))
    course = storage.create_course(name, request.form.get("description", "").strip())
    return redirect(url_for("course_detail", course_id=course["id"]))


@app.route("/courses/<course_id>")
def course_detail(course_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        flash("Course not found.")
        return redirect(url_for("index"))
    return render_template("course.html", course=course)


@app.route("/courses/<course_id>/upload", methods=["POST"])
def upload_file(course_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        return redirect(url_for("index"))
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a file to upload.")
        return redirect(url_for("course_detail", course_id=course_id))
    if not extractors.allowed_file(file.filename):
        flash("Unsupported file type. Use PDF, Word (.docx), text or Markdown.")
        return redirect(url_for("course_detail", course_id=course_id))
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_DIR, f"{course_id}_{int(time.time())}_{filename}")
    file.save(path)
    try:
        text = extractors.extract_text(path)
    except Exception as e:
        flash(f"Could not read file: {e}")
        return redirect(url_for("course_detail", course_id=course_id))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if not text.strip():
        flash("No readable text found in that file.")
        return redirect(url_for("course_detail", course_id=course_id))
    course["notes"].append({
        "id": storage.new_id(),
        "title": filename,
        "source": "file",
        "content": text,
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    storage.update_course(course)
    flash(f"Added notes from {filename}.")
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/courses/<course_id>/paste", methods=["POST"])
def paste_notes(course_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        return redirect(url_for("index"))
    content = request.form.get("content", "").strip()
    if not content:
        flash("Paste some notes first.")
        return redirect(url_for("course_detail", course_id=course_id))
    title = request.form.get("title", "").strip() or "Pasted notes"
    course["notes"].append({
        "id": storage.new_id(),
        "title": title,
        "source": "paste",
        "content": content,
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    storage.update_course(course)
    flash("Notes added.")
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/courses/<course_id>/notes/<note_id>/delete", methods=["POST"])
def delete_note(course_id, note_id):
    course = storage.get_course(storage.load(), course_id)
    if course:
        course["notes"] = [n for n in course["notes"] if n["id"] != note_id]
        storage.update_course(course)
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/courses/<course_id>/generate", methods=["POST"])
def generate_material(course_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        return redirect(url_for("index"))
    if not course["notes"]:
        flash("Add some notes before generating study material.")
        return redirect(url_for("course_detail", course_id=course_id))
    text = "\n\n".join(n["content"] for n in course["notes"])
    settings = storage.get_settings()
    try:
        result = generator.generate(text, settings)
    except ValueError as e:
        flash(f"AI generation failed ({e}). Falling back to offline generation.")
        result = generator.rule_based_generate(text)
    if not result["flashcards"] and not result["mcqs"]:
        flash("Could not generate material from these notes. Try adding more descriptive text.")
        return redirect(url_for("course_detail", course_id=course_id))
    replace = request.form.get("replace") == "1"
    if replace:
        course["flashcards"] = []
        course["quiz"] = []
    course["flashcards"].extend(result["flashcards"])
    course["quiz"].extend(result["mcqs"])
    storage.update_course(course)
    mode = "AI" if (settings.get("ai_enabled") and settings.get("api_key")) else "offline rule-based"
    flash(f"Generated {len(result['flashcards'])} flashcards and {len(result['mcqs'])} quiz questions ({mode}).")
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/courses/<course_id>/delete", methods=["POST"])
def delete_course_route(course_id):
    storage.delete_course(course_id)
    flash("Course deleted.")
    return redirect(url_for("index"))


@app.route("/courses/<course_id>/study")
def study(course_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        return redirect(url_for("index"))
    shuffle = request.args.get("shuffle") == "1"
    only_review = request.args.get("review") == "1"
    cards = [c for c in course["flashcards"] if (not only_review) or (not c.get("got_it"))]
    if shuffle:
        import random
        cards = list(cards)
        random.shuffle(cards)
    return render_template("study.html", course=course, cards=cards, shuffle=shuffle, only_review=only_review)


@app.route("/courses/<course_id>/cards/<card_id>/mark", methods=["POST"])
def mark_card(course_id, card_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        return jsonify(ok=False), 404
    got_it = request.form.get("got_it") == "1"
    for card in course["flashcards"]:
        if card["id"] == card_id:
            card["got_it"] = got_it
            storage.update_course(course)
            return jsonify(ok=True, got_it=got_it)
    return jsonify(ok=False), 404


@app.route("/courses/<course_id>/reset-progress", methods=["POST"])
def reset_progress(course_id):
    course = storage.get_course(storage.load(), course_id)
    if course:
        for card in course["flashcards"]:
            card["got_it"] = False
        storage.update_course(course)
    return redirect(url_for("course_detail", course_id=course_id))


@app.route("/courses/<course_id>/quiz")
def quiz(course_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        return redirect(url_for("index"))
    import random
    questions = list(course["quiz"])
    random.shuffle(questions)
    return render_template("quiz.html", course=course, questions=questions)


@app.route("/courses/<course_id>/quiz/submit", methods=["POST"])
def submit_quiz(course_id):
    course = storage.get_course(storage.load(), course_id)
    if not course:
        return redirect(url_for("index"))
    answers = request.form.to_dict()
    results = []
    correct = 0
    for q in course["quiz"]:
        submitted = answers.get(q["id"])
        is_correct = submitted is not None and int(submitted) == q["answer"]
        if is_correct:
            correct += 1
        results.append({
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"],
            "submitted": int(submitted) if submitted is not None else None,
            "correct": is_correct,
            "explanation": q.get("explanation", ""),
        })
    total = len(course["quiz"])
    score = round(100 * correct / total) if total else 0
    course["attempts"].append({
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "score": score,
        "correct": correct,
        "total": total,
    })
    storage.update_course(course)
    return render_template("quiz_results.html", course=course, results=results, score=score, correct=correct, total=total)


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        current = storage.get_settings()
        current["ai_enabled"] = request.form.get("ai_enabled") == "on"
        current["api_key"] = request.form.get("api_key", "").strip()
        current["base_url"] = request.form.get("base_url", "").strip() or "https://api.openai.com/v1"
        current["model"] = request.form.get("model", "").strip() or "gpt-4o-mini"
        storage.save_settings(current)
        flash("Settings saved.")
        return redirect(url_for("settings_page"))
    return render_template("settings.html", settings=storage.get_settings())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
