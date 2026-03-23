"""
pdf_builder.py

Generates a "Jeremy Mode" drill context PDF from the analyzed missed questions.
The PDF contains:
  1. How-to instructions for the user
  2. AI system prompt (Jeremy Mode persona + session rules)
  3. Personalized miss data (every concept missed, with teaching point)

Users paste the full PDF text into any chatbot to get a personalized
NBME-style drill session in Jeremy Mode.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY


# ── static prompt sections ─────────────────────────────────────────────────────

PROMPT_SECTIONS = [
    (
        "IDENTITY & TONE",
        "You are Jeremy Mode — a high-energy, meme-friendly, intensely supportive medical "
        "education AI tutor. You are like that one classmate who somehow makes 6am studying "
        "feel like a hype session. Use ALL CAPS for emphasis. Call the user 'chief' or 'doc'. "
        "Celebrate correct answers loudly. Respond to wrong answers with encouragement + a "
        "crystal-clear explanation. Keep the energy HIGH throughout. You are OBSESSED with "
        "helping them crush this shelf exam."
    ),
    (
        "SESSION STRUCTURE",
        "1. Open with a SHORT motivational intro (2-3 sentences max).\n"
        "2. Tell the user you have their personalized miss data loaded and will drill their weak spots.\n"
        "3. Give questions ONE AT A TIME. Never batch them.\n"
        "4. Wait for the user's answer before revealing the correct answer.\n"
        "5. After each answer: celebrate if correct, explain if wrong.\n"
        "6. After every 5 questions: give a quick progress update ('3/5 chief — you're building!').\n"
        "7. Flag wrong answers for re-test: 'Marking this one for later.'\n"
        "8. Keep going until the user says stop."
    ),
    (
        "QUESTION STYLE — NBME FORMAT",
        "Write clinical vignette questions:\n"
        "- Lead with patient demographics, presenting complaint, relevant history, exam findings, labs\n"
        "- End with 'Which of the following is the most likely diagnosis?' or 'most appropriate next step?'\n"
        "- Provide 4-5 answer choices (A-E) with plausible distractors\n"
        "- Base ALL questions on the PERSONALIZED MISS DATA section below\n"
        "- Weight toward categories with MORE misses\n"
        "- Occasionally re-test concepts in a slightly different clinical presentation"
    ),
    (
        "ANSWERING PROTOCOL",
        "CORRECT ANSWER:\n"
        "Celebrate with energy ('YESSSS chief!! That's EXACTLY right!!!'). Give a 1-2 sentence "
        "pearl reinforcing WHY it's correct. Then immediately present the next question.\n\n"
        "WRONG ANSWER:\n"
        "Never make them feel bad ('Good instinct but not quite, doc!'). Explain EXACTLY why "
        "the correct answer is right and why their answer was wrong. Flag it: "
        "'Marking this one for a re-test later.' Then present the next question."
    ),
]


# ── main builder ───────────────────────────────────────────────────────────────

def build_jeremy_pdf(analyzed: list[dict], meta: dict, output_path: str) -> None:
    """
    Build the Jeremy Mode PDF from analyzed miss data.

    Args:
        analyzed:    List of dicts from Claude analysis (topic, category, teaching_point, etc.)
        meta:        Exam metadata (exam_name, date, score)
        output_path: Where to write the PDF
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
    )

    # ── styles ─────────────────────────────────────────────────────────────────
    title_style = ParagraphStyle("JTitle",
        fontSize=26, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1a3a5c"),
        alignment=TA_CENTER, spaceAfter=4)

    subtitle_style = ParagraphStyle("JSub",
        fontSize=11, fontName="Helvetica",
        textColor=colors.HexColor("#2196F3"),
        alignment=TA_CENTER, spaceAfter=18)

    body_style = ParagraphStyle("JBody",
        fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#222222"),
        leading=15, spaceAfter=5,
        alignment=TA_JUSTIFY)

    howto_style = ParagraphStyle("JHowTo",
        fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#333333"),
        leading=16, spaceAfter=4)

    miss_title_style = ParagraphStyle("JMissTitle",
        fontSize=10, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1a3a5c"),
        spaceAfter=1)

    miss_body_style = ParagraphStyle("JMissBody",
        fontSize=9.5, fontName="Helvetica",
        textColor=colors.HexColor("#333333"),
        leading=14, spaceAfter=6,
        leftIndent=12)

    white_bold = ParagraphStyle("WBold",
        fontSize=11, fontName="Helvetica-Bold", textColor=colors.white)

    cat_label = ParagraphStyle("CatLabel",
        fontSize=10, fontName="Helvetica-Bold", textColor=colors.white)

    closing_style = ParagraphStyle("JClosing",
        fontSize=13, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1a3a5c"),
        alignment=TA_CENTER, spaceAfter=0)

    # ── helpers ────────────────────────────────────────────────────────────────
    def banner(text: str, bg: str = "#1a3a5c", style=None) -> Table:
        if style is None:
            style = white_bold
        t = Table([[Paragraph(text, style)]], colWidths=[6.8 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ]))
        return t

    story = []

    # ── title ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("JEREMY MODE", title_style))

    exam_name = meta.get("exam_name", "NBME Self-Assessment")
    exam_date = meta.get("date", "")
    exam_score = meta.get("score", "")
    subtitle_parts = [exam_name]
    if exam_date:
        subtitle_parts.append(exam_date)
    if exam_score:
        subtitle_parts.append(f"Score: {exam_score}")
    story.append(Paragraph(" · ".join(subtitle_parts), subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor("#2196F3"), spaceAfter=14))

    # ── how to use ────────────────────────────────────────────────────────────
    story.append(banner("HOW TO USE THIS DOCUMENT"))
    story.append(Spacer(1, 8))

    steps = [
        "1.  <b>Copy the entire contents of this PDF</b> and paste into your preferred AI chatbot "
        "(ChatGPT, Claude, Gemini, etc.).",
        "2.  Type: <b>\"Start Jeremy Mode — drill my weak spots.\"</b>",
        "3.  The AI will quiz you <b>one question at a time</b>, weighted toward your missed concepts.",
        "4.  Answer each question, get feedback, keep going until you're done.",
        "5.  The AI will re-test flagged questions throughout the session.",
    ]
    for step in steps:
        story.append(Paragraph(step, howto_style))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1,
                             color=colors.HexColor("#e0e0e0"), spaceAfter=14))

    # ── AI instructions ───────────────────────────────────────────────────────
    story.append(banner("AI INSTRUCTIONS — PASTE EVERYTHING BELOW THIS LINE",
                         bg="#2196F3"))
    story.append(Spacer(1, 10))

    for section_title, section_body in PROMPT_SECTIONS:
        story.append(banner(f"[ {section_title} ]"))
        story.append(Spacer(1, 6))
        for line in section_body.split("\n"):
            if line.strip():
                story.append(Paragraph(line, body_style))
            else:
                story.append(Spacer(1, 4))
        story.append(Spacer(1, 10))

    # ── topic weighting — built from actual data ───────────────────────────────
    story.append(banner("[ TOPIC WEIGHTING ]"))
    story.append(Spacer(1, 6))

    # count misses by category
    cat_counts: dict[str, int] = {}
    for item in analyzed:
        cat = item.get("category", "Other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    sorted_cats = sorted(cat_counts.items(), key=lambda x: -x[1])
    total_misses = len(analyzed)

    story.append(Paragraph(
        f"Focus questions toward these categories (ranked by miss frequency across {total_misses} total misses):",
        body_style))
    story.append(Spacer(1, 4))

    for rank, (cat, count) in enumerate(sorted_cats, 1):
        story.append(Paragraph(
            f"{rank}. {cat} — {count} miss{'es' if count > 1 else ''}",
            body_style))

    story.append(Spacer(1, 14))

    # ── personalized miss data ─────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1.5,
                             color=colors.HexColor("#2196F3"), spaceAfter=10))
    story.append(banner("PERSONALIZED MISS DATA — CONCEPTS TO DRILL",
                         bg="#2196F3"))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "These are the EXACT concepts this student missed. Build questions from these topics. "
        "Each entry includes the concept and the key teaching point.",
        ParagraphStyle("intro", fontSize=9.5, fontName="Helvetica-Oblique",
                       textColor=colors.HexColor("#555"), leading=14, spaceAfter=10)))

    # group by category, preserving rank order
    grouped: dict[str, list[dict]] = {}
    for item in analyzed:
        cat = item.get("category", "Other")
        grouped.setdefault(cat, []).append(item)

    # emit in rank order (most misses first)
    for cat, _ in sorted_cats:
        items = grouped.get(cat, [])
        count = len(items)

        # category banner
        cat_table = Table(
            [[Paragraph(f"{cat}  ({count} miss{'es' if count > 1 else ''})", cat_label)]],
            colWidths=[6.8 * inch])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#37474f")),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ]))
        story.append(KeepTogether([cat_table, Spacer(1, 4)]))

        for item in items:
            topic    = item.get("topic", "Unknown concept")
            teaching = item.get("teaching_point", "")
            block = [
                Paragraph(f"• {topic}", miss_title_style),
                Paragraph(teaching, miss_body_style),
            ]
            story.append(KeepTogether(block))

        story.append(Spacer(1, 8))

    # ── footer ─────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=2,
                             color=colors.HexColor("#2196F3"), spaceAfter=10))
    story.append(Paragraph(
        "JEREMY MODE ENGAGED, CHIEF. Let's get this shelf. \U0001f525",
        closing_style))

    doc.build(story)
