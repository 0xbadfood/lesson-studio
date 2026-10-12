# Phase 1 corpus audit

- Verdict: **BLOCKED**
- Catalog fingerprint: `0e36f4e12fa03c79166f2208aa90385d884ec7adeb79b2daa89df05a977a1686`
- Generated: `2026-10-09T04:37:26.668591+00:00`
- Scope: English, Classes 11-12
- Checks: hashes=yes, pdfinfo=yes, native-text probe=yes

## Summary

| Measure | Count |
|---|---:|
| Official books | 79 |
| Expected chapters | 628 |
| Ready for knowledge banks | 522 |
| Blocked chapters | 106 |
| Expected prelims | 79 |
| Missing prelims | 12 |

## Readiness by class

| Class | Expected | Ready | Blocked |
|---:|---:|---:|---:|
| 11 | 342 | 266 | 76 |
| 12 | 286 | 256 | 30 |

## Native text triage

| Status | Chapters |
|---|---:|
| `not_probed` | 106 |
| `usable` | 522 |

This probe samples the opening pages. A usable native layer does not eliminate page-level OCR or visual inspection during knowledge-bank construction.

## Findings

| Finding | Documents | Blocking for chapters |
|---|---:|---|
| `missing_file` | 118 | yes |

Encrypted Class 10 Mathematics PDFs are not blocked when PDF parsing, text extraction, and rendering work. The flag remains recorded for provenance.

## Missing chapter groups

| Class | Subject | Book | Code | Missing suffixes | Count |
|---:|---|---|---|---|---:|
| 11 | Computers and Communication Technology | CCT Part-I | `kect1` | 01, 02, 03, 04, 05, 06, 07, 08 | 8 |
| 11 | Computers and Communication Technology | CCT Part-II | `kect2` | 01, 02, 03, 04, 05, 06 | 6 |
| 11 | English | Hornbill | `kehb1` | 07, 08, 09, 10 | 4 |
| 11 | English | Woven Words | `keww1` | 09, 10, 23, 24, 25, 26, 27 | 7 |
| 11 | Graphics design | The story of graphic design | `kegd1` | 01, 02, 03, 04, 05, 06, 07, 08 | 8 |
| 11 | Heritage Crafts | Living Craft Traditions of India | `kehc1` | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10 | 10 |
| 11 | Vocational | General Duty Assistant | `keda1` | 01, 02, 03, 04, 05 | 5 |
| 11 | Vocational | Dairy Farmer Enterpreneur | `kedf1` | 01, 02, 03, 04 | 4 |
| 11 | Vocational | Floriculturist | `kefc1` | 01, 02, 03, 04, 05, 06 | 6 |
| 11 | Vocational | Floriculturist | `keoc1` | 01, 02, 03, 04, 05, 06 | 6 |
| 11 | Vocational | Floriculturist- Protected Cultivation | `kepc1` | 01, 02, 03, 04, 05 | 5 |
| 11 | Vocational | Vision Technician | `kevt1` | 01, 02, 03, 04, 05, 06, 07 | 7 |
| 12 | English | Flamingo | `lefl1` | 09, 10 | 2 |
| 12 | English | Kaliedoscope | `lekl1` | 06, 07, 08, 09, 10, 19, 20 | 7 |
| 12 | Heritage Crafts | Craft Tradition of India | `lehc1` | 01, 02, 03, 04, 05, 06, 07, 08, 09 | 9 |
| 12 | New Age Graphics Design | New Age Graphics Design | `legd1` | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12 | 12 |

## Missing prelim groups

Missing prelims do not block chapter knowledge banks, but remain corpus findings:

- Class 11 · Computers and Communication Technology · CCT Part-I (`kect1ps`)
- Class 11 · Computers and Communication Technology · CCT Part-II (`kect2ps`)
- Class 11 · Graphics design · The story of graphic design (`kegd1ps`)
- Class 11 · Heritage Crafts · Living Craft Traditions of India (`kehc1ps`)
- Class 11 · Vocational · General Duty Assistant (`keda1ps`)
- Class 11 · Vocational · Dairy Farmer Enterpreneur (`kedf1ps`)
- Class 11 · Vocational · Floriculturist (`kefc1ps`)
- Class 11 · Vocational · Floriculturist (`keoc1ps`)
- Class 11 · Vocational · Floriculturist- Protected Cultivation (`kepc1ps`)
- Class 11 · Vocational · Vision Technician (`kevt1ps`)
- Class 12 · Heritage Crafts · Craft Tradition of India (`lehc1ps`)
- Class 12 · New Age Graphics Design · New Age Graphics Design (`legd1ps`)

## Freeze decision

Phase 1 cannot yet be frozen: 106 expected English chapter records need an official recovery, an explicitly provenanced legacy backfill, or a reviewed stale-catalog exclusion.
