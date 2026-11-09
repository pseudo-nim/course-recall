"""Flashcard and MCQ generation: offline rule-based engine plus optional AI mode."""
import json
import random
import re
import urllib.error
import urllib.request

STOPWORDS = set(
    """a an the and or but if then else when while of for to in on at by with from as is are was were be been being
    it its this that these those they them their there here which who whom whose what how why not no nor so such than
    too very can could will would should may might must do does did done have has had also into about over under
    between during through above below up down out off again further once all any both each few more most other
    some only own same just because we you he she i us our your his her my me him""".split()
)

DEFINITION_PATTERNS = [
    r"^(?P<term>[A-Z][\w \-]{2,60}?)\s+(?:is|are|was|were|refers to|means|describes|denotes)\s+(?P<def>.+)$",
]

MCQ_OPTION_COUNT = 4


def _sentences(text):
    cleaned = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [p.strip() for p in parts if len(p.strip()) > 25]


def _key_terms(text):
    counts = {}
    for match in re.findall(r"\b[A-Za-z][A-Za-z\-]{3,}\b", text):
        word = match.strip()
        if word.lower() in STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    terms = [w for w, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]
    return terms[:40]


def _title_case_variants(term):
    return {term, term.lower(), term.capitalize(), term.title()}


def rule_based_generate(text, max_cards=12, max_mcqs=8):
    sentences = _sentences(text)
    terms = _key_terms(text)
    flashcards = []
    mcqs = []
    seen_terms = set()

    definition_pairs = []
    for sent in sentences:
        for pattern in DEFINITION_PATTERNS:
            m = re.match(pattern, sent.strip(), re.IGNORECASE)
            if m:
                term = m.group("term").strip().rstrip(".,;:")
                definition = m.group("def").strip().rstrip(".,;")
                if 2 < len(term) < 60 and len(definition) > 10:
                    definition_pairs.append((term, definition, sent))
                break

    for term, definition, source in definition_pairs:
        key = term.lower()
        if key in seen_terms:
            continue
        seen_terms.add(key)
        flashcards.append({
            "id": f"fc_{len(flashcards)}_{random.randint(1000, 9999)}",
            "front": f"What is {term}?",
            "back": definition,
            "source": source,
            "got_it": False,
        })
        if len(flashcards) >= max_cards:
            break

    term_pool = [t for t, _, _ in definition_pairs] + terms
    distractor_pool = [t for t in term_pool if t.lower() not in seen_terms]

    for term, definition, source in definition_pairs:
        if len(mcqs) >= max_mcqs:
            break
        distractors = [d for d in distractor_pool if d.lower() != term.lower()]
        if len(distractors) < MCQ_OPTION_COUNT - 1:
            continue
        wrong = random.sample(distractors, MCQ_OPTION_COUNT - 1)
        correct = f"{definition}"
        options = [correct] + [f"A concept related to {w}." for w in wrong]
        random.shuffle(options)
        mcqs.append({
            "id": f"q_{len(mcqs)}_{random.randint(1000, 9999)}",
            "question": f"Which statement best describes {term}?",
            "options": options,
            "answer": options.index(correct),
            "explanation": f"Source material: \"{source}\"",
        })

    if len(flashcards) < max_cards:
        for sent in sentences:
            if len(flashcards) >= max_cards:
                break
            for term in term_pool:
                if len(flashcards) >= max_cards:
                    break
                if any(v in sent for v in _title_case_variants(term)) and len(term) > 4:
                    pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
                    if pattern.search(sent):
                        cloze = pattern.sub("_____", sent, count=1)
                        flashcards.append({
                            "id": f"fc_{len(flashcards)}_{random.randint(1000, 9999)}",
                            "front": f"Fill in the blank: {cloze}",
                            "back": term,
                            "source": sent,
                            "got_it": False,
                        })
                        break

    if len(mcqs) < max_mcqs and len(terms) >= MCQ_OPTION_COUNT:
        for sent in sentences:
            if len(mcqs) >= max_mcqs:
                break
            candidates = [t for t in terms if re.search(r"\b" + re.escape(t) + r"\b", sent, re.IGNORECASE)]
            if not candidates:
                continue
            answer_term = candidates[0]
            distractors = [t for t in terms if t.lower() != answer_term.lower()]
            if len(distractors) < MCQ_OPTION_COUNT - 1:
                continue
            wrong = random.sample(distractors, MCQ_OPTION_COUNT - 1)
            options = [answer_term] + wrong
            random.shuffle(options)
            mcqs.append({
                "id": f"q_{len(mcqs)}_{random.randint(1000, 9999)}",
                "question": f"Which term appears in this statement? \"{sent[:200]}\"",
                "options": options,
                "answer": options.index(answer_term),
                "explanation": f"The statement directly mentions \"{answer_term}\".",
            })

    return {"flashcards": flashcards, "mcqs": mcqs}


def ai_generate(text, settings, max_cards=12, max_mcqs=8):
    api_key = settings.get("api_key", "")
    base_url = settings.get("base_url", "").rstrip("/")
    model = settings.get("model", "gpt-4o-mini")
    if not api_key:
        raise ValueError("AI mode is enabled but no API key is set in Settings.")

    prompt = (
        "You are a study assistant. Given course notes, generate study material as strict JSON.\n"
        'Return JSON of the form {"flashcards": [{"front": str, "back": str, "source": str}], '
        '"mcqs": [{"question": str, "options": [str, str, str, str], "answer": int, "explanation": str}]} '
        f"with at most {max_cards} flashcards and {max_mcqs} MCQs. "
        '"answer" is the 0-based index of the correct option in "options". '
        "The explanation must say why the correct answer is right.\n\nNOTES:\n" + text[:12000]
    )
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        raise ValueError(f"AI API returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise ValueError(f"Could not reach the AI API: {e}")

    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError("AI response did not contain JSON.")
    data = json.loads(match.group(0))

    flashcards = []
    for i, card in enumerate(data.get("flashcards", [])[:max_cards]):
        flashcards.append({
            "id": f"fc_ai{i}_{random.randint(1000, 9999)}",
            "front": str(card.get("front", "")).strip(),
            "back": str(card.get("back", "")).strip(),
            "source": str(card.get("source", "")).strip(),
            "got_it": False,
        })
    mcqs = []
    for i, q in enumerate(data.get("mcqs", [])[:max_mcqs]):
        options = [str(o) for o in q.get("options", [])]
        answer = q.get("answer", -1)
        if len(options) >= 2 and isinstance(answer, int) and 0 <= answer < len(options):
            mcqs.append({
                "id": f"q_ai{i}_{random.randint(1000, 9999)}",
                "question": str(q.get("question", "")).strip(),
                "options": options,
                "answer": answer,
                "explanation": str(q.get("explanation", "")).strip(),
            })
    return {"flashcards": flashcards, "mcqs": mcqs}


def generate(text, settings, max_cards=12, max_mcqs=8):
    if settings.get("ai_enabled") and settings.get("api_key"):
        return ai_generate(text, settings, max_cards, max_mcqs)
    return rule_based_generate(text, max_cards, max_mcqs)
