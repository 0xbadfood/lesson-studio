#!/usr/bin/env python3
"""Textbook knowledge base: what an NCERT chapter teaches, where it falls short, and what fills the gaps.

The textbook sets what students at a level must learn and how far it goes; it does not limit what a lesson may
say. This experiment turns one chapter (optionally narrowed to a topic) into the three inputs a lesson planner
needs, every item traceable to where it came from:

  1. brief    - what the textbook teaches: objectives, concepts, laws, formulas, derivations and examples, each
                with its pages and a short verbatim quote that code checks against the page text; the textbook's
                notation; its depth (derived, stated, mentioned); what it leaves out.
  2. gaps     - where the textbook falls short for a learner: missing intuition, skipped steps, assumed
                prerequisites, unaddressed misconceptions, missing context or scale, things only motion can show,
                oversimplifications. Each gap names the brief items it supports and whether it needs research.
  3. augment  - what fills each gap: from standard knowledge, or from bounded web research (the search agent:
                Tavily + Obscura) with citations to pages actually fetched. Each item says whether it is within
                the level or an extension, and must not contradict the textbook.

Model calls go to an OpenAI-compatible Qwen server (default: the local vLLM on :7001). Every call is cached under
the output folder, so a rerun only repeats what changed.

  kb_research/env/bin/python kb_research/textbook_kb.py --chapter keph1:05
  kb_research/env/bin/python kb_research/textbook_kb.py --chapter keph1:05 --topic "work-energy theorem"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from scivid import curriculum  # noqa: E402
from scivid.llm import Chat  # noqa: E402
from scivid.settings import Settings  # noqa: E402

import search_agent  # noqa: E402

LOCAL = 'http://127.0.0.1:7001/v1'
OUT = HERE.parent / 'textbook-kb'
KINDS = ('concept', 'definition', 'law', 'formula', 'derivation', 'example', 'activity', 'application', 'fact')
DEPTHS = ('derived', 'stated', 'mentioned')
GAP_TYPES = ('intuition', 'skipped_step', 'prerequisite', 'misconception', 'context', 'visual',
             'oversimplification', 'history')
LEVELS = ('within', 'extension')
MAX_RESEARCH = 6

SYSTEM = 'You are an expert science and mathematics teacher and curriculum analyst. Reply with JSON only.'


# ------------------------------------------------------------------ helpers
def words(text):
    """Lower-case alphanumeric tokens: quotes are matched on these so line breaks and hyphenation do not matter."""
    return re.findall(r'[a-z0-9]+', (text or '').lower().replace('-\n', ''))


def _in_order(q, p):
    """The words q appear in p in order within a short span (gaps allowed)."""
    span = 3 * len(q) + 30
    for start, w in enumerate(p):
        if w != q[0]:
            continue
        at, end = 1, start + 1
        while at < len(q) and end < min(len(p), start + span):
            if p[end] == q[at]:
                at += 1
            end += 1
        if at == len(q):
            return True
    return False


def quoted(quote, page_text):
    """True when the quote is on the page. The text comes from two-column PDFs: extraction can drop a block of the
    other column (an equation, a caption) into a sentence, or put a sentence's end before its start. So the words
    must appear in order within a short span, or as two such pieces of at least 4 words each. An invented quote
    does not find its words that way."""
    q, p = words(quote), words(page_text)
    if len(q) < 3:
        return False
    if _in_order(q, p):
        return True
    return any(_in_order(q[:k], p) and _in_order(q[k:], p) for k in range(4, len(q) - 3))


def find_quote(quote, pages, cited):
    """The page a quote is really on: a cited page or a neighbour (models cite worked examples one page off), with
    neighbouring pages joined so a sentence running onto the next page still matches. None when not found."""
    by_page = {p['page']: p['text'] for p in pages}
    for page in cited:
        if quoted(quote, by_page.get(page, '')):
            return page
    for page in cited:
        for near in (page - 1, page + 1):
            if quoted(quote, by_page.get(near, '')):
                return near
        joined = ' '.join(by_page.get(n, '') for n in (page - 1, page, page + 1))
        if quoted(quote, joined):
            return page
    return None


def audience(cls):
    return f'Class {cls} students in India (NCERT/CBSE)'


def page_block(pages):
    return '\n'.join(f'[PAGE {p["page"]}]\n{p["text"]}' for p in pages)


def ids(items, prefix):
    return [i.get('id') for i in items] == [f'{prefix}{n + 1}' for n in range(len(items))]


def raise_if(errors):
    if errors:
        raise ValueError('; '.join(errors[:25]))


# ------------------------------------------------------------------ 1. brief
def brief_errors(brief, pages):
    by_page = {p['page']: p['text'] for p in pages}
    errors = []
    teaches = brief.get('teaches') or []
    if not 5 <= len(teaches) <= 45:
        errors.append(f'"teaches" must list 5-45 items (got {len(teaches)})')
    if not ids(teaches, 'T'):
        errors.append('teaches ids must be T1, T2, ... in order')
    for t in teaches:
        tid = t.get('id')
        if t.get('kind') not in KINDS:
            errors.append(f'{tid}: kind must be one of {list(KINDS)}')
        if t.get('depth') not in DEPTHS:
            errors.append(f'{tid}: depth must be one of {list(DEPTHS)}')
        cited = [p for p in t.get('pages') or [] if p in by_page]
        if not cited or len(cited) != len(t.get('pages') or []):
            errors.append(f'{tid}: pages must be page numbers of this chapter (1-{max(by_page)})')
        else:
            found = find_quote(t.get('quote', ''), pages, cited)
            if found is None:
                errors.append(f'{tid}: the quote "{t.get("quote", "")}" is not on page(s) {cited} or next to them; '
                              'copy 4-25 consecutive words of prose exactly as printed (not an equation)')
            elif found not in cited:
                t['pages'] = sorted(set(cited) | {found})   # record where the quote really is
    objectives = brief.get('objectives') or []
    if not ids(objectives, 'O'):
        errors.append('objective ids must be O1, O2, ... in order')
    known = {t.get('id') for t in teaches}
    for o in objectives:
        bad = [x for x in o.get('covers') or [] if x not in known]
        if bad or not o.get('covers'):
            errors.append(f'{o.get("id")}: "covers" must list the teaches ids it needs (unknown: {bad})')
    bad_order = [x for x in brief.get('order') or [] if x not in known]
    if bad_order:
        errors.append(f'"order" has unknown ids {bad_order}')
    return errors


BRIEF_SCHEMA = '''{"scope":str (what this brief covers: the chapter, or the topic within it),
"objectives":[{"id":"O1","text":str,"covers":["T1",...]}],
"teaches":[{"id":"T1","kind":"concept|definition|law|formula|derivation|example|activity|application|fact",
  "title":str,"statement":str (what the textbook teaches, faithfully, including any formula in plain notation),
  "depth":"derived|stated|mentioned","pages":[int],"quote":str (4-25 consecutive words copied exactly from that page's prose)}],
"notation":[{"symbol":str,"meaning":str,"unit":str,"pages":[int]}],
"conventions":[str] (sign conventions, assumptions, idealisations the textbook uses),
"order":["T1",...] (the textbook's teaching order),
"leaves_out":[str] (what the textbook says it does not treat, defers to later classes, or marks as beyond the syllabus)}'''


def make_brief(model, chapter, pages, bank, topic):
    focus = (f'Cover only what the chapter teaches about this topic, plus anything in the chapter the topic depends '
             f'on: "{topic}".' if topic else 'Cover the whole chapter.')
    bank_part = ''
    if bank:
        bank_part = ('\nKNOWLEDGE BANK (read from the page images by a vision model; use it to read equations and '
                     'figures that the extracted text garbles; quotes must still come from the page text):\n' +
                     json.dumps({k: bank.get(k) for k in ('chapter_summary', 'key_concepts', 'learning_progression',
                                                          'grounded_facts', 'important_visuals')},
                                ensure_ascii=False)[:30000])
    prompt = (
        f'Write the TEACHING BRIEF of NCERT Class {chapter["class"]} {chapter["book_title"]}, Chapter '
        f'{chapter["chapter"]} "{chapter["title"]}": exactly what the textbook teaches, at the depth it teaches it. '
        f'{focus} Be faithful: report what the book says, not what you would add (gaps come later). Mark depth: '
        '"derived" when the book proves or derives it, "stated" when it gives it without proof, "mentioned" when it '
        'only names it. Include worked examples that teach a method. Formulas in plain text (v^2 = u^2 + 2as). '
        'Page numbers are the [PAGE n] markers below. The page text was extracted from the PDF, so equations may be '
        'garbled: read them through the surrounding prose and the knowledge bank, and quote prose, never equations.'
        f'\nReturn JSON: {BRIEF_SCHEMA}\nCHAPTER PAGES:\n{page_block(pages)}{bank_part}')
    return model.call('brief', prompt, thinking=0, max_tokens=20000, attempts=4, system=SYSTEM,
                      validate=lambda b: raise_if(brief_errors(b, pages)))


# ------------------------------------------------------------------ 2. gaps
def gap_errors(result, brief):
    known = {t['id'] for t in brief['teaches']}
    gaps = result.get('gaps') or []
    errors = []
    if not 3 <= len(gaps) <= 16:
        errors.append(f'list 3-16 gaps (got {len(gaps)})')
    if not ids(gaps, 'G'):
        errors.append('gap ids must be G1, G2, ... in order')
    for g in gaps:
        gid = g.get('id')
        if g.get('type') not in GAP_TYPES:
            errors.append(f'{gid}: type must be one of {list(GAP_TYPES)}')
        bad = [x for x in g.get('about') or [] if x not in known]
        if bad or not g.get('about'):
            errors.append(f'{gid}: "about" must list the brief ids it supports (unknown: {bad})')
        if g.get('resolve') not in ('knowledge', 'research'):
            errors.append(f'{gid}: resolve must be "knowledge" or "research"')
        if g.get('resolve') == 'research' and len(str(g.get('research_question', '')).split()) < 5:
            errors.append(f'{gid}: a research gap needs a specific research_question')
    if sum(g.get('resolve') == 'research' for g in gaps) > MAX_RESEARCH:
        errors.append(f'at most {MAX_RESEARCH} gaps may need research; resolve the rest from standard knowledge')
    return errors


GAP_SCHEMA = '''{"gaps":[{"id":"G1","type":"intuition|skipped_step|prerequisite|misconception|context|visual|oversimplification|history",
"about":["T3",...],"missing":str (what exactly a learner does not get from the textbook here),
"why_it_matters":str,"priority":"high|medium|low",
"resolve":"knowledge|research","research_question":str (only for research: a specific, searchable question)}]}'''


def make_gaps(model, chapter, brief, topic):
    prompt = (
        f'This is the teaching brief of an NCERT chapter for {audience(chapter["class"])}. The textbook defines '
        'what must be taught at this level, but every textbook has gaps. Find where THIS textbook falls short for '
        'a learner meeting the ideas for the first time' + (f', for the topic "{topic}"' if topic else '') + ':\n'
        '- intuition: a law or formula given without the "why";\n'
        '- skipped_step: a derivation or worked example that jumps over a step a learner would stall on;\n'
        '- prerequisite: an idea the book assumes but students at this level often lack;\n'
        '- misconception: a common wrong idea the book never confronts;\n'
        '- context: missing real-world use, scale or numbers that make the idea matter;\n'
        '- visual: something that only motion or change over time shows well (the lesson is an animated video);\n'
        '- oversimplification: a statement that is simplified in a way that can mislead later (flag it; the '
        'lesson will still teach the textbook version first);\n'
        '- history: how the idea was discovered, only where it helps understanding.\n'
        'Report real, specific gaps, not generic advice; rank them by priority. Use "research" only when filling '
        'the gap needs facts, numbers or data you should verify from sources (real-world values, applications, '
        'history); use "knowledge" for explanations a good teacher knows.\n'
        f'Return JSON: {GAP_SCHEMA}\nBRIEF:\n{json.dumps(brief, ensure_ascii=False)}')
    return model.call('gaps', prompt, thinking=6000, max_tokens=8000, attempts=3, system=SYSTEM,
                      validate=lambda r: raise_if(gap_errors(r, brief)))


# ------------------------------------------------------------------ 3. research + augment
RESEARCH_PROMPT = search_agent.SYSTEM_PROMPT.replace(
    'You are a careful internet research agent.',
    'You are a careful internet research agent helping a teacher prepare a lesson for school students.') + (
    '7. Prefer sources a teacher can trust: universities, science agencies (NASA, ISRO, NIST, CERN), standards '
    'bodies, encyclopaedias and textbooks. Give concrete values with units and say what they depend on.\n')


def obscura():
    """The page fetcher: beside this file on the AI server, in the kbagent folder on the Spark."""
    local = HERE / 'obscura'
    return (local if local.is_file() else Path(Settings.from_env().kbagent_root) / 'obscura').resolve()


def run_research(gap, chapter, out, qwen_url, model_id, api_key, tavily_key, log):
    path = out / 'research' / f'{gap["id"]}.json'
    if path.exists():
        saved = json.loads(path.read_text())
        if not (saved.get('error') and not saved.get('fetched')):     # nothing fetched: try again
            return saved
    question = (f'{gap["research_question"]}\n(Context: preparing a lesson for {audience(chapter["class"])} on '
                f'"{chapter["title"]}". The point to support: {gap["missing"]})')
    tools = search_agent.ResearchTools(tavily=search_agent.TavilyClient(api_key=tavily_key),
                                       obscura_path=obscura(), max_searches=2, max_fetches=5)
    qwen = search_agent.QwenClient(qwen_url, model_id, api_key, timeout=600)
    started = time.monotonic()
    try:
        result = search_agent.research(question, qwen, tools, max_steps=16, system_prompt=RESEARCH_PROMPT)
    except search_agent.HarnessError as exc:
        result = {'question': question, 'error': str(exc), 'cited': [], 'fetched': sorted(tools.fetched_urls),
                  'searches_used': tools.searches_used, 'fetches_used': tools.fetches_used}
    result['seconds'] = round(time.monotonic() - started, 1)
    log(f'  research {gap["id"]}: {result["searches_used"]} searches, {result["fetches_used"]} fetches, '
        f'{len(result["cited"])} cited, {result["seconds"]} s' + (f' - {result["error"]}' if 'error' in result else ''))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    return result


def augment_errors(result, gaps, research):
    errors = []
    items = result.get('augmentations') or []
    want = [g['id'] for g in gaps]
    got = [a.get('gap') for a in items]
    if sorted(got) != sorted(want):
        errors.append(f'give exactly one augmentation per gap {want} (got {got})')
    for a in items:
        gid = a.get('gap')
        if a.get('level') not in LEVELS:
            errors.append(f'{gid}: level must be "within" or "extension"')
        if a.get('provenance') not in ('standard_knowledge', 'web'):
            errors.append(f'{gid}: provenance must be "standard_knowledge" or "web"')
        if len(str(a.get('content', '')).split()) < 25:
            errors.append(f'{gid}: content must be a teachable explanation (at least 25 words)')
        allowed = set(map(search_agent.canonical_url, (research.get(gid) or {}).get('fetched', [])))
        sources = a.get('sources') or []
        if a.get('provenance') == 'web':
            bad = [u for u in sources if search_agent.canonical_url(u) not in allowed]
            if not sources or bad:
                errors.append(f'{gid}: web sources must be pages fetched for this gap (not fetched: {bad[:3]})')
        elif sources:
            errors.append(f'{gid}: standard_knowledge has no sources; use provenance "web" to cite')
    return errors


AUGMENT_SCHEMA = '''{"augmentations":[{"gap":"G1","title":str,"content":str (the explanation, steps, values or story a
teacher would add, written to be taught: precise, with units and numbers where relevant),
"level":"within|extension","provenance":"standard_knowledge|web","sources":[url],
"textbook_note":str (how it sits with the textbook: e.g. "keeps the textbook's sign convention", or the textbook
simplification it refines and how to present both)}]}'''


def make_augment(model, chapter, brief, gaps, research):
    findings = {gid: {k: r.get(k) for k in ('answer', 'cited', 'fetched', 'error')} for gid, r in research.items()}
    prompt = (
        f'Fill each gap in this NCERT chapter for {audience(chapter["class"])}. For each gap write what a teacher '
        'adds: the missing intuition, the skipped steps worked in full, the prerequisite in brief, the misconception '
        'and its correction, real values with units, the history. Rules: never contradict the textbook (when it '
        'simplifies, keep its version and present the refinement as such); keep its notation and conventions; '
        '"within" if it is at this class level, "extension" if it goes beyond the syllabus (the lesson will label '
        'it). Use the research findings for gaps that were researched and cite only their fetched pages '
        '(provenance "web"); for the others use standard knowledge (no sources). If a research finding is missing '
        'or unreliable, use standard knowledge and do not invent figures.\n'
        f'Return JSON: {AUGMENT_SCHEMA}\nBRIEF:\n{json.dumps(brief, ensure_ascii=False)}\n'
        f'GAPS:\n{json.dumps(gaps, ensure_ascii=False)}\nRESEARCH FINDINGS:\n{json.dumps(findings, ensure_ascii=False)}')
    return model.call('augment', prompt, thinking=6000, max_tokens=14000, attempts=3, system=SYSTEM,
                      validate=lambda r: raise_if(augment_errors(r, gaps, research)))


# ------------------------------------------------------------------ output
def markdown(kb):
    c, brief = kb['chapter'], kb['brief']
    by_gap = {a['gap']: a for a in kb['augmentations']}
    lines = [f'# {c["title"]}', f'NCERT Class {c["class"]} · {c["book_title"]} · Chapter {c["chapter"]}'
             + (f' · topic: {kb["topic"]}' if kb['topic'] else ''), '', f'_Scope: {brief.get("scope", "")}_', '',
             '## 1. What the textbook teaches', '']
    for o in brief.get('objectives', []):
        lines.append(f'- **{o["id"]}** {o["text"]} ({", ".join(o["covers"])})')
    lines.append('')
    for t in brief['teaches']:
        lines.append(f'- **{t["id"]} · {t["title"]}** ({t["kind"]}, {t["depth"]}, p.{", ".join(map(str, t["pages"]))})'
                     f' — {t["statement"]}')
    if brief.get('notation'):
        lines += ['', '**Notation:** ' + '; '.join(f'{n["symbol"]} = {n["meaning"]}' + (f' ({n["unit"]})' if n.get('unit') else '')
                                                  for n in brief['notation'])]
    if brief.get('conventions'):
        lines += ['', '**Conventions:** ' + '; '.join(brief['conventions'])]
    if brief.get('leaves_out'):
        lines += ['', '**Leaves out:** ' + '; '.join(brief['leaves_out'])]
    lines += ['', '## 2. Gaps', '']
    for g in kb['gaps']:
        lines.append(f'- **{g["id"]} · {g["type"]}** ({g.get("priority", "")}, about {", ".join(g["about"])}) — '
                     f'{g["missing"]} _Why: {g.get("why_it_matters", "")}_')
    lines += ['', '## 3. Augmented knowledge', '']
    for g in kb['gaps']:
        a = by_gap.get(g['id'])
        if not a:
            continue
        lines += [f'### {g["id"]} · {a["title"]} ({a["level"]}, {a["provenance"].replace("_", " ")})', '', a['content'], '']
        if a.get('textbook_note'):
            lines += [f'_Textbook: {a["textbook_note"]}_', '']
        if a.get('sources'):
            lines += ['Sources: ' + ', '.join(a['sources']), '']
    return '\n'.join(lines) + '\n'


def tavily_key():
    if os.environ.get('TAVILY_API_KEY'):
        return os.environ['TAVILY_API_KEY']
    service = Path(Settings.from_env().remotion_root) / '.service.env'
    for line in service.read_text().splitlines() if service.exists() else []:
        if line.startswith('TAVILY_API_KEY='):
            return shlex.split(line.partition('=')[2])[0]
    raise SystemExit('Set TAVILY_API_KEY (or keep it in the remotion .service.env)')


def build(chapter_ref, topic='', endpoint=LOCAL, out_root=OUT, log=print):
    settings = Settings.from_env()
    chapter = curriculum.find(settings.ncert_root, chapter_ref)
    slug = re.sub(r'[^a-z0-9]+', '-', topic.lower()).strip('-')[:50] if topic else 'chapter'
    out = Path(out_root) / chapter['id'].replace(':', '-') / slug
    out.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get('VLLM_API_KEY') if endpoint.startswith('http://127.0.0.1') else None
    model = Chat(endpoint, out, label='qwen', api_key=api_key, local=True, timeout=1800)
    pages = [p for p in curriculum.chapter_pages(chapter) if p['text'].strip()]
    bank = curriculum.knowledge_bank(chapter)
    log(f'{chapter["id"]} "{chapter["title"]}": {len(pages)} pages, knowledge bank: {"yes" if bank else "no"}')
    timings = {}

    started = time.monotonic()
    brief = make_brief(model, chapter, pages, bank, topic)
    timings['brief'] = round(time.monotonic() - started, 1)
    log(f'brief: {len(brief["teaches"])} items, {len(brief.get("objectives", []))} objectives ({timings["brief"]} s)')

    started = time.monotonic()
    gaps = make_gaps(model, chapter, brief, topic)['gaps']
    timings['gaps'] = round(time.monotonic() - started, 1)
    log(f'gaps: {len(gaps)} ({sum(g["resolve"] == "research" for g in gaps)} need research) ({timings["gaps"]} s)')

    started = time.monotonic()
    research = {}
    todo = [g for g in gaps if g['resolve'] == 'research']
    if todo:
        key, model_id = tavily_key(), model._model(search_agent.httpx.Client(
            timeout=30, headers={'Authorization': f'Bearer {api_key}'} if api_key else {}))
        for g in todo:
            research[g['id']] = run_research(g, chapter, out, endpoint, model_id, api_key, key, log)
    timings['research'] = round(time.monotonic() - started, 1)

    started = time.monotonic()
    augmentations = make_augment(model, chapter, brief, gaps, research)['augmentations']
    timings['augment'] = round(time.monotonic() - started, 1)
    log(f'augmentations: {len(augmentations)} ({timings["augment"]} s)')

    kb = {'schema': 'textbook_kb_v1', 'chapter': {k: chapter[k] for k in ('id', 'class', 'subject', 'book_title',
                                                                          'chapter', 'title')},
          'topic': topic, 'endpoint': endpoint, 'model': model.model, 'knowledge_bank_used': bool(bank),
          'timings_seconds': timings, 'brief': brief, 'gaps': gaps, 'augmentations': augmentations,
          'research': research}
    (out / 'kb.json').write_text(json.dumps(kb, indent=1, ensure_ascii=False))
    (out / 'kb.md').write_text(markdown(kb))
    log(f'wrote {out / "kb.md"}')
    return kb


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--chapter', required=True, help='Lesson Studio chapter id, e.g. keph1:05')
    parser.add_argument('--topic', default='', help='narrow the brief to one topic within the chapter')
    parser.add_argument('--endpoint', default=LOCAL, help='OpenAI-compatible Qwen base URL')
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args(argv)
    build(args.chapter, args.topic, args.endpoint, args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
