"""
scraper.py — Playwright-based NBME score report scraper.

Navigates to a starttest.com score report URL, clicks "Review Incorrect Items",
then iterates through each wrong question collecting:
  - question number
  - full stem text
  - answer choices
  - student's selected answer
  - correct answer
  - explanation text (if visible)
"""

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import re
import time


def scrape_incorrect_items(url: str) -> tuple[list[dict], dict]:
    """
    Scrape all incorrect items from an NBME starttest.com score report.

    Returns:
        misses: list of dicts with question data
        meta:   dict with exam name, date, score
    """
    misses = []
    meta   = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()

        # ── load the score report ──────────────────────────────────────────
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # grab metadata from the summary page
        try:
            meta["exam_name"] = page.inner_text("h2, h3, .exam-title").strip()[:80]
        except Exception:
            meta["exam_name"] = "Family Medicine Self-Assessment"

        try:
            full_text = page.inner_text("body")
            # extract score
            score_match = re.search(r"Assessment Score[:\s]+(\d+)", full_text)
            if score_match:
                meta["score"] = score_match.group(1)
            # extract date
            date_match = re.search(r"(?:Test Date|Date)[:\s]+([\d/]+)", full_text)
            if date_match:
                meta["date"] = date_match.group(1)
        except Exception:
            pass

        # ── click Review Incorrect Items ───────────────────────────────────
        try:
            page.click("text=Review Incorrect Items", timeout=8000)
        except PlaywrightTimeout:
            # try finding in iframe
            for frame in page.frames:
                try:
                    frame.click("text=Review Incorrect Items", timeout=3000)
                    break
                except Exception:
                    continue

        page.wait_for_timeout(2000)

        # ── determine which frame has the exam content ─────────────────────
        content_frame = page
        for frame in page.frames:
            try:
                title = frame.title()
                if "Question" in title or "Exam Block" in title:
                    content_frame = frame
                    break
            except Exception:
                continue

        # ── iterate through incorrect questions ────────────────────────────
        q_number = 0
        max_questions = 60  # safety cap
        empty_fetches = 0

        while q_number < max_questions:
            page.wait_for_timeout(800)

            # get current question number from title or header
            try:
                page_title = page.title()
                qnum_match = re.search(r"Question (\d+) of (\d+)", page_title)
                if qnum_match:
                    current_q = int(qnum_match.group(1))
                    total_q   = int(qnum_match.group(2))
                    meta["total_questions"] = total_q
                else:
                    current_q = q_number + 1
            except Exception:
                current_q = q_number + 1

            # scrape question content from whatever frame has it
            question_data = _scrape_question(page)

            if question_data:
                question_data["question_number"] = current_q
                misses.append(question_data)
                q_number += 1
                empty_fetches = 0
            else:
                empty_fetches += 1
                if empty_fetches >= 3:
                    # definitively failed to find question 3 times = done
                    break
                page.wait_for_timeout(2000)
                continue

            # check if there's a Next button to click
            next_clicked = False
            for frame in [page] + page.frames:
                try:
                    next_btn = frame.query_selector("button:has-text('Next'), a:has-text('Next')")
                    if next_btn and next_btn.is_visible():
                        next_btn.click()
                        next_clicked = True
                        break
                except Exception:
                    continue

            if not next_clicked:
                break

            # detect if we looped back to score report
            page.wait_for_timeout(1000)
            try:
                if "Score Report" in page.title() and "Question" not in page.title():
                    break
            except Exception:
                break

        browser.close()

    return misses, meta


def _scrape_question(page) -> dict | None:
    """Extract question stem, choices, selected answer, and correct answer from current page."""
    result = {}

    # try main page first, then each frame
    sources = [page] + page.frames

    for source in sources:
        try:
            body_text = source.inner_text("body")
        except Exception:
            continue

        # must look like a question page
        if "Correct Answer" not in body_text and "correct answer" not in body_text.lower():
            continue

        # ── stem ──────────────────────────────────────────────────────────
        try:
            # grab all paragraphs that look like the stem (before choices)
            stem_el = source.query_selector(".stem, .question-text, p")
            if stem_el:
                result["stem"] = stem_el.inner_text().strip()
            else:
                # fallback: grab first big chunk before the answer choices
                lines = [l.strip() for l in body_text.split("\n") if l.strip()]
                stem_lines = []
                for line in lines:
                    if re.match(r"^[A-F]\.", line):
                        break
                    stem_lines.append(line)
                result["stem"] = " ".join(stem_lines[:20])
        except Exception:
            result["stem"] = ""

        # ── answer choices ─────────────────────────────────────────────────
        choices = {}
        choice_matches = re.findall(r"([A-F])\.\s+(.+?)(?=\n[A-F]\.|Correct Answer|$)", body_text, re.DOTALL)
        for letter, text in choice_matches:
            choices[letter] = text.strip().replace("\n", " ")[:200]
        result["choices"] = choices

        # ── correct answer ─────────────────────────────────────────────────
        correct_match = re.search(r"Correct Answer[:\s]+([A-F])", body_text)
        if correct_match:
            letter = correct_match.group(1)
            result["correct_answer_letter"] = letter
            result["correct_answer_text"]   = choices.get(letter, "")

        # ── student's selected answer (filled radio = their pick) ──────────
        # On the page, the student's answer is shown with a filled circle
        # We identify it by checking which radio is "checked" in the DOM
        student_letter = None
        try:
            for frame in [source]:
                radios = frame.query_selector_all("input[type='radio']:checked")
                for radio in radios:
                    # get the label text next to this radio
                    parent = radio.evaluate("el => el.parentElement?.innerText || ''")
                    letter_match = re.match(r"([A-F])\.", parent.strip())
                    if letter_match:
                        student_letter = letter_match.group(1)
                        break
        except Exception:
            pass

        # fallback: look for the filled dot indicator in text
        if not student_letter:
            # The filled choice often appears differently in the DOM
            # Look for which choice has a distinct marker
            try:
                filled = source.query_selector("[class*='selected'], [class*='chosen'], [class*='student']")
                if filled:
                    text = filled.inner_text().strip()
                    m = re.match(r"([A-F])\.", text)
                    if m:
                        student_letter = m.group(1)
            except Exception:
                pass

        result["your_answer_letter"] = student_letter or "?"
        result["your_answer_text"]   = choices.get(student_letter, "") if student_letter else ""

        # ── explanation ────────────────────────────────────────────────────
        try:
            exp_match = re.search(r"Correct Answer[:\s]+[A-F]\.?\s*\n+(.*?)(?:\n\n|\Z)", body_text, re.DOTALL)
            if exp_match:
                result["explanation"] = exp_match.group(1).strip()[:500]
        except Exception:
            result["explanation"] = ""

        # only return if we got meaningful content
        if result.get("stem") and result.get("correct_answer_letter"):
            return result

    return None
