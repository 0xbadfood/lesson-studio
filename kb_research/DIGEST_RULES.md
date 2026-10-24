# Digest rules (any curriculum, any subject)

The user's rule, 24 Oct 2026:

> accept book -> break chapters -> break concepts -> store exercise questions -> store answers -> store figures in
> the image index -> link exercises back to the last concept the exercise tests.
> This should be true for any curriculum, any subject.

DIGEST_FORMAT.md describes the record layout. This file sets the steps every book goes through and the rules each
step keeps, whoever published the book. Books include NCERT, ICSE (Selina and others), state boards, and a school's
own upload.

## The steps

| # | Step | Produces | Today |
|---|---|---|---|
| 1 | Accept the book | `source`: curriculum or board, publisher, class, subject, title, edition, language, file hash, the rights record | NCERT only. `source` has no curriculum or publisher field yet; NCERT is assumed |
| 2 | Break into chapters | one digest per chapter, with the book's own number and title | NCERT ships one PDF per chapter. Detecting chapters in a whole-book PDF is not built |
| 3 | Read the pages | `blocks`: everything the page teaches, in the book's words, each with its pages and a quote anchor | `digest.py`, from page images plus the text layer (OCR when the layer is unusable) |
| 4 | Break into concepts | `concepts`: the units a learner would choose, in book order, each pointing at its blocks | `digest.py make_concepts` |
| 5 | Store the exercise questions | one block per question (`type: exercise`), with the book's label, kind, pages and any figure it names | all exercise blocks, end-of-chapter and in-text |
| 6 | Store the answers | the book's own answer for each question, with its source page | `book_extras.py answers` → `answers.json` |
| 7 | Store the figures in the image index | one PNG per figure (teaching and exercise figures), with label, caption, page and box | `book_extras.py figures` → `figures.json`, `figures/`, `extras.sqlite3` |
| 8 | Link each exercise to the last concept it tests | `primary`: the latest concept in book order the question needs; the others are what it builds on | Not yet. Exercises link to every concept they practise (Classes 9–12: 4,013 to one concept, 315 to several, 2 to none) |
| 9 | Gaps, additions, visual needs | what the book leaves out, and checked additions that fill it | `digest.py`, `visual_needs.py` |

## Rules every step keeps

1. **The book is the authority.** Steps 3 and 5–7 record only what the book prints. Nothing is invented:
   - an unanswered question stays unanswered;
   - a figure that can't be found is recorded as missing.

   Model-made content belongs only in additions (step 9), and is marked as such.
2. **Use the book's own labels.** Chapter numbers, section numbers, "Exercise 5.23", "Fig. 5.10", "Q4(b)" are kept
   as printed.
   - Matching (answers to questions, figures to the questions that name them) goes by these labels.
   - Label patterns differ by publisher. NCERT prints "Exercise 7.1 Q4"; Selina-style books print "Exercise 2(A)",
     with its own question numbering. Each publisher gets its own pattern, not a hard-coded NCERT one.
3. **Everything traces to a page.** Every block, answer and figure carries its pages. Quotes are checked by code
   against the page text: the text layer, or OCR text for scanned books.
4. **Code checks completeness.** Code counts the numbered things on each page (sections, equations, examples,
   figures, questions) and requires one block for each.
5. **Read the PDF once.** After a chapter is digested, the pipeline reads the digest, the sidecars and the image index,
   never the PDF. Re-reading costs model time that has already been paid.
6. **The digest record is stable.** Answers and figures live in sidecars beside `digest.json`, not inside it, so a
   rebuilt digest keeps them. Every model call is cached, so a re-run repeats only what changed.
7. **Every question practises one primary concept.** It is the last concept in book order that the question tests.
   The earlier concepts it needs are listed, not primary. Concept films offer the question as practice, and a solution
   video links back to that concept's film.
8. **Subject-neutral blocks.** Humanities chapters use their own block types (event, person, source, map), while
   science and maths use theirs. The steps stay the same. A chapter without numbered sections is still one chapter.
   A lettered item like "(d) Winds" belongs to the section it sits in.
9. **Rights before reading.** Step 1 records who may use the book:
   - catalogue books are ones we may use for everyone;
   - an uploaded book stays with the school that uploaded it and confirmed its rights.

## Notes for the books to come

- **ICSE Classes 8–10 (Selina and others)** are rich in questions: exercises A, B and C, MCQs and numericals.
  - The sample `selina-class-10-physics-chapter-2-work-energy-and-power.pdf` (28 pages) is a scan. Its only text
    layer is the download site's watermark, so step 3 needs OCR text for its quote checks.
  - That copy came from a third-party site. Using Selina books in the shared catalogue needs the publisher's licence.
    A school uploading its own copy is the tenant path (rule 9).
- **OCR candidate: `baidu/Qianfan-OCR`** (Apache-2.0, released March 2026). Bench it against tesseract and our page
  reader on that scan before relying on it.
