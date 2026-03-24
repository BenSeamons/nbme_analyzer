import os
import json
import time
import sqlite3
import zipfile
import tempfile
import shutil
import anthropic
from flask import Flask, render_template, request, jsonify, send_file, session
from scraper import scrape_incorrect_items
from pdf_builder import build_jeremy_pdf

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


# ── Claude analysis ────────────────────────────────────────────────────────────

def analyze_with_claude(misses: list[dict]) -> list[dict]:
    prompt = f"""You are a medical education expert analyzing NBME missed questions.

Below are {len(misses)} questions a medical student got wrong on an NBME Family Medicine
Clinical Science Self-Assessment. For each question provide:
1. A short topic label (e.g. "Polymyalgia Rheumatica", "Panic Disorder vs MVP")
2. The category (e.g. "Rheumatology", "Behavioral Health", "Cardiology")
3. A clear teaching point: WHY the correct answer is right and why the student's
   answer was wrong. 2-4 sentences, punchy and memorable.
4. An Anki card front (NBME-style clinical vignette question, concise)
5. An Anki card back (correct answer + structured explanation, HTML ok)

Return ONLY a valid JSON array, no markdown, no backticks. Each element:
{{
  "question_number": int,
  "topic": "short topic name",
  "category": "system category",
  "your_answer_letter": "letter student chose",
  "your_answer_text": "text of student answer",
  "correct_answer_letter": "correct letter",
  "correct_answer_text": "text of correct answer",
  "teaching_point": "2-4 sentence explanation",
  "anki_front": "HTML clinical vignette question",
  "anki_back": "HTML structured answer with teaching points"
}}

Missed questions:
{json.dumps(misses, indent=2)}
"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── Anki builder ───────────────────────────────────────────────────────────────

def build_apkg(cards: list[dict], deck_name: str = "NBME Missed Questions") -> tuple[str, str]:
    tmpdir  = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "collection.anki2")

    DECK_ID  = int(time.time() * 1000) % (2**31)
    MODEL_ID = (DECK_ID + 1) % (2**31)
    NOW      = int(time.time())
    NOW_MS   = int(time.time() * 1000)

    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.executescript("""
    CREATE TABLE col (id integer PRIMARY KEY, crt integer, mod integer, scm integer,
        ver integer, dty integer, usn integer, ls integer,
        conf text, models text, decks text, dconf text, tags text);
    CREATE TABLE notes (id integer PRIMARY KEY, guid text NOT NULL, mid integer NOT NULL,
        mod integer NOT NULL, usn integer NOT NULL, tags text NOT NULL,
        flds text NOT NULL, sfld text NOT NULL, csum integer NOT NULL,
        flags integer NOT NULL, data text NOT NULL);
    CREATE TABLE cards (id integer PRIMARY KEY, nid integer NOT NULL, did integer NOT NULL,
        ord integer NOT NULL, mod integer NOT NULL, usn integer NOT NULL,
        type integer NOT NULL, queue integer NOT NULL, due integer NOT NULL,
        ivl integer NOT NULL, factor integer NOT NULL, reps integer NOT NULL,
        lapses integer NOT NULL, left integer NOT NULL, odue integer NOT NULL,
        odid integer NOT NULL, flags integer NOT NULL, data text NOT NULL);
    CREATE TABLE revlog (id integer PRIMARY KEY, cid integer NOT NULL, usn integer NOT NULL,
        ease integer NOT NULL, ivl integer NOT NULL, lastIvl integer NOT NULL,
        factor integer NOT NULL, time integer NOT NULL, type integer NOT NULL);
    CREATE TABLE graves (usn integer NOT NULL, oid integer NOT NULL, type integer NOT NULL);
    CREATE INDEX ix_notes_usn ON notes (usn);
    CREATE INDEX ix_cards_usn ON cards (usn);
    CREATE INDEX ix_cards_nid ON cards (nid);
    CREATE INDEX ix_cards_sched ON cards (did, queue, due);
    CREATE INDEX ix_revlog_usn ON revlog (usn);
    CREATE INDEX ix_revlog_cid ON revlog (cid);
    """)

    model = {str(MODEL_ID): {
        "id": MODEL_ID, "name": "NBME Missed", "type": 0,
        "mod": NOW, "usn": -1, "sortf": 0, "did": DECK_ID,
        "tmpls": [{"name": "Card 1", "ord": 0,
            "qfmt": '<div style="font-family:Georgia,serif;font-size:16px;max-width:700px;margin:auto;padding:10px;">{{Front}}</div>',
            "afmt": '<div style="font-family:Georgia,serif;font-size:15px;max-width:700px;margin:auto;padding:10px;">{{FrontSide}}<hr style="border:1px solid #ccc;margin:15px 0;"><div style="background:#f0f7ff;border-left:4px solid #2196F3;padding:10px;border-radius:4px;">{{Back}}</div></div>',
            "did": None, "bqfmt": "", "bafmt": ""}],
        "flds": [
            {"name": "Front", "ord": 0, "sticky": False, "rtl": False, "font": "Arial", "size": 20},
            {"name": "Back",  "ord": 1, "sticky": False, "rtl": False, "font": "Arial", "size": 20}
        ],
        "css": ".card{font-family:Georgia,serif;font-size:16px;text-align:left;color:#222;background:#fff;padding:15px;} table{width:100%;border-collapse:collapse;margin:8px 0;} th{background:#2196F3;color:white;padding:5px 8px;} td{padding:4px 8px;} tr:nth-child(even){background:#f5f5f5;}",
        "latexPre": "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amssymb,amsmath}\n\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n",
        "latexPost": "\\end{document}", "req": [[0, "any", [0]]]
    }}

    deck = {str(DECK_ID): {
        "id": DECK_ID, "name": deck_name, "desc": "Generated by NBME Analyzer",
        "mod": NOW, "usn": -1,
        "lrnToday": [0,0], "revToday": [0,0], "newToday": [0,0], "timeToday": [0,0],
        "collapsed": False, "browserCollapsed": False,
        "extendNew": 10, "extendRev": 50, "conf": 1, "dyn": 0
    }}

    dconf = {"1": {"id":1,"mod":0,"name":"Default","usn":-1,"maxTaken":60,"timer":0,
        "autoplay":True,"replayq":True,
        "new":{"bury":True,"delays":[1,10],"initialFactor":2500,"ints":[1,4,7],"order":0,"perDay":50},
        "rev":{"bury":True,"ease4":1.3,"ivlFct":1,"maxIvl":36500,"perDay":200,"hardFactor":1.2},
        "lapse":{"delays":[10],"leechAction":1,"leechFails":8,"minInt":1,"mult":0}}}

    cur.execute("INSERT INTO col VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        1, NOW, NOW, NOW_MS, 11, 0, 0, 0,
        json.dumps({"activeDecks":[DECK_ID],"curDeck":DECK_ID,"newSpread":0,
                    "collapseTime":1200,"timeLim":0,"estTimes":True,"dueCounts":True,
                    "curModel":MODEL_ID,"nextPos":1,"sortType":"noteFld","sortBackwards":False}),
        json.dumps(model), json.dumps(deck), json.dumps(dconf), "{}"))

    for i, card in enumerate(cards):
        nid   = NOW_MS + i * 1000
        cid   = NOW_MS + i * 1000 + 500
        front = card.get("anki_front", "")
        back  = card.get("anki_back", "")
        tags  = f"{card.get('category','').replace(' ','-')} NBME-Miss"
        flds  = front + "\x1f" + back
        csum  = sum(ord(c) for c in front[:10]) % (2**32)
        cur.execute("INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (nid, f"nbme{i:05d}", MODEL_ID, NOW, -1, tags, flds, front[:100], csum, 0, ""))
        cur.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, nid, DECK_ID, 0, NOW, -1, 0, 0, i, 0, 2500, 0, 0, 0, 0, 0, 0, ""))

    conn.commit()
    conn.close()

    with open(os.path.join(tmpdir, "media"), "w") as f:
        json.dump({}, f)

    apkg_path = os.path.join(tmpdir, "nbme_missed.apkg")
    with zipfile.ZipFile(apkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, "collection.anki2")
        zf.write(os.path.join(tmpdir, "media"), "media")

    return apkg_path, tmpdir


# ── routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    url  = data.get("url", "").strip()

    if not url or ("starttest.com" not in url and "amazonaws.com" not in url):
        return jsonify({"error": "Please paste a valid NBME score report URL (starttest.com or amazonaws.com)."}), 400

    try:
        misses, meta = scrape_incorrect_items(url)

        if not misses:
            return jsonify({
                "error": "No incorrect items found, or the URL has expired. "
                         "Please get a fresh URL from NBME Insights."
            }), 400

        analyzed = analyze_with_claude(misses)

        categories = {}
        for item in analyzed:
            cat = item.get("category", "Other")
            categories[cat] = categories.get(cat, 0) + 1

        session["analyzed"]  = analyzed
        session["meta"]      = meta
        session["deck_name"] = f"NBME {meta.get('exam_name', 'Missed Questions')}"

        return jsonify({
            "meta":         meta,
            "misses":       analyzed,
            "categories":   dict(sorted(categories.items(), key=lambda x: -x[1])),
            "total_missed": len(analyzed),
        })

    except Exception as e:
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500


@app.route("/download-anki")
def download_anki():
    analyzed  = session.get("analyzed", [])
    deck_name = session.get("deck_name", "NBME Missed Questions")

    if not analyzed:
        return "No analysis data found. Please analyze a report first.", 400

    apkg_path, tmpdir = build_apkg(analyzed, deck_name)
    try:
        return send_file(
            apkg_path,
            as_attachment=True,
            download_name="NBME_Missed_Questions.apkg",
            mimetype="application/vnd.anki"
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.route("/download-pdf")
def download_pdf():
    analyzed = session.get("analyzed", [])
    meta     = session.get("meta", {})

    if not analyzed:
        return "No analysis data found. Please analyze a report first.", 400

    tmpdir   = tempfile.mkdtemp()
    pdf_path = os.path.join(tmpdir, "jeremy_mode.pdf")
    try:
        build_jeremy_pdf(analyzed, meta, pdf_path)
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name="Jeremy_Mode_Drill.pdf",
            mimetype="application/pdf"
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
