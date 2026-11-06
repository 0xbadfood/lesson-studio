#!/usr/bin/env python3
"""Molecules a chapter names -> textbook-digest/<chapter>/molecules.json, the candidates for Bondwork's named index.

A model reads the chapter's digest blocks and lists every specific molecule, ion and intermediate the book names,
with the book's own name and formula spelling, the IUPAC name and an isomeric SMILES. RDKit checks each answer
here (the SMILES parses; the structure's formula is the formula the book prints), and a wrong one goes back to the
model with what is wrong. Bondwork's build-index checks the candidates again (its guards, and OPSIN reading the
IUPAC name independently) before any of them enters the index.

  .venv/bin/python kb_research/molecule_index.py kech2-02 kech2-03
The model is a Lesson Studio connection (MOLECULE_MODEL overrides; default Opus on OpenRouter, as the digest's
auditor uses). Every call is cached under the chapter's folder.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem.rdMolDescriptors import CalcMolFormula

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from scivid import models  # noqa: E402

RDLogger.DisableLog('rdApp.*')
OUT = HERE.parent / 'textbook-digest'
SCIVID_DATA = HERE.parent / 'scivid-data'
MODEL = os.environ.get('MOLECULE_MODEL') or 'claude-opus-5-5-openrouter'
CHUNK = 30000            # characters of blocks per call: a chapter is two to four calls
ATTEMPTS = 3            # the last one keeps the species that pass and sets the rest aside
KINDS = ('molecule', 'ion', 'radical', 'intermediate', 'complex', 'ionic')

SCHEMA = '''{"molecules":[{"name":str (the name the book uses, as printed: "acetic acid", "tert-butyl alcohol", "ethene"),
"aliases":[str] (other names the book uses for it, and its common or IUPAC name if the book gives another),
"iupac":str (the systematic IUPAC name, with stereodescriptors when the book means one stereoisomer: "(2E)-but-2-ene"),
"formula":str (the formula as the book prints it, in ASCII: "CH3COOH", "(CH3)3C-OH", "SO4^2-", "[Co(NH3)6]^3+";
 "" when the book prints none),
"smiles":str (isomeric SMILES of exactly that species: charges on atoms, stereo only when the book specifies it),
"kind":"molecule|ion|radical|intermediate|complex|ionic",
"blocks":[str] (ids of the blocks that name it)}]}'''

PROMPT = '''Below are blocks transcribed from NCERT Class {cls} {book}, Chapter {no} "{title}". List every SPECIFIC chemical
species the blocks name or draw: molecules, ions, radicals, reaction intermediates (carbocations, carbanions, free
radicals), complexes and ionic compounds. One entry per species; gather every block that names it.

Leave out: classes and families ("alkanes", "alcohols", "haloarenes"); general formulas and R groups (RCOOH, CnH2n+2,
R-X); species the book says do not exist (He2 and Ne2, bond order zero); polymers; mixtures and minerals with no
single formula; elements named only as elements (sodium metal, chlorine the element is fine as Cl2 when the book
writes Cl2).

Write the formula exactly as the book prints it (condensed formulas as printed: CH3CH2OH, not C2H6O). Charges after
^ (SO4^2-, NH4^+, CH3^+). When the book names stereoisomers (cis/trans, E/Z, R/S, d/l), list each as its own entry
with the stereo in its IUPAC name and in its SMILES.

Return JSON only: {schema}

BLOCKS:
{blocks}'''


# groups and ligands books write by name (Ph, en, py, edta): Bondwork's catalog spells them out the same way
GROUPS = [(r'Ph(?![a-z])', 'C6H5'), (r'Me(?![a-z])', 'CH3'), (r'Et(?![a-z])', 'C2H5'), (r'(?<![A-Za-z])en(?![a-z])', 'C2H8N2'),
          (r'(?<![A-Za-z])py(?![a-z])', 'C5H5N'), (r'(?<![A-Za-z])ox(?![a-z])', 'C2O4'), (r'(?<![A-Za-z])gly(?![a-z])', 'C2H4NO2'),
          (r'(?<![A-Za-z])acac(?![a-z])', 'C5H7O2'), (r'(?<![A-Za-z])(?:edta|EDTA)(?![a-z])', 'C10H12N2O8')]


def spelled_out(text):
    """A book formula with its named groups written as atoms, and a trailing position tag (-o, -m, -p) dropped."""
    text = re.sub(r'[-\s][omp]$', '', text.strip())
    for pattern, atoms in GROUPS:
        text = re.sub(pattern, f'({atoms})', text)
    return text


def counts(text):
    """Element counts of a condensed formula: bracketed groups with multipliers, bond marks ignored, hydrates added."""
    text = re.sub(r'[-=≡–—]', '', spelled_out(text))
    main, *hydrates = re.split(r'[·.*]', text)
    stack = [{}]
    for el, k1, opening, closing, k2 in re.findall(r'([A-Z][a-z]?)([0-9]*)|([(\[])|([)\]])([0-9]*)', main):
        if opening:
            stack.append({})
        elif closing:
            group = stack.pop()
            for e, n in group.items():
                stack[-1][e] = stack[-1].get(e, 0) + n * int(k2 or 1)
        elif el:
            stack[-1][el] = stack[-1].get(el, 0) + int(k1 or 1)
    out = dict(stack[0])
    for h in hydrates:
        times, rest = re.match(r'([0-9]*)(.*)', h).groups()
        for e, n in counts(rest).items():
            out[e] = out.get(e, 0) + n * int(times or 1)
    return out


def book_formula(text):
    """(element counts, charge) of a formula as the book prints it, with the charge after ^ (SO4^2-) or a bare sign."""
    body, _, charge = text.partition('^')
    if not charge and text.endswith(('+', '-')):
        body, charge = text[:-1], text[-1]
    sign = re.match(r'([0-9]*)([+-])', charge) if charge else None
    return counts(body), (int(sign.group(1) or 1) * (1 if sign.group(2) == '+' else -1)) if sign else 0


# p-block atoms from period 3 down may hold more than eight electrons (ClF3, BrF5, IF7, KrF2, XeF4): RDKit's valence
# table refuses many of them, so they are checked by electron count instead
EXPANDS = {'Al', 'Si', 'P', 'S', 'Cl', 'Ge', 'As', 'Se', 'Br', 'Kr', 'Sn', 'Sb', 'Te', 'I', 'Xe', 'Rn'}
VALENCE_ELECTRONS = {'Al': 3, 'Si': 4, 'Ge': 4, 'Sn': 4, 'P': 5, 'As': 5, 'Sb': 5, 'S': 6, 'Se': 6, 'Te': 6,
                     'Cl': 7, 'Br': 7, 'I': 7, 'Kr': 8, 'Xe': 8, 'Rn': 8}


def parse(smiles):
    """The molecule a SMILES names, or None. When RDKit's valence table refuses it, every atom but the
    octet-expanding ones is checked by RDKit as usual, and those by electron count: the bonds and charge may not need
    more valence electrons than the atom has."""
    if not (smiles or '').strip():
        return None                      # RDKit reads '' as a molecule with no atoms
    mol = Chem.MolFromSmiles(smiles)
    if mol is not None:
        return mol
    raw = Chem.MolFromSmiles(smiles, sanitize=False)
    if raw is None or not any(a.GetSymbol() in EXPANDS for a in raw.GetAtoms()):
        return None
    rest = Chem.RWMol(raw)
    for atom in rest.GetAtoms():
        if atom.GetSymbol() in EXPANDS:
            atom.SetAtomicNum(0)
            atom.SetNoImplicit(True)
    try:
        Chem.SanitizeMol(rest)
    except Exception:
        return None
    for atom in raw.GetAtoms():
        if atom.GetSymbol() in EXPANDS:
            used = sum(b.GetBondTypeAsDouble() for b in atom.GetBonds()) + atom.GetNumExplicitHs()
            if VALENCE_ELECTRONS[atom.GetSymbol()] - atom.GetFormalCharge() - used < 0:
                return None
            atom.SetNoImplicit(True)
    raw.UpdatePropertyCache(strict=False)
    Chem.SanitizeMol(raw, Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
    return raw


def structure_formula(mol):
    """Element counts and charge; deuterium and tritium count as D and T, as books write them (D2O, ND3)."""
    m = Chem.AddHs(mol)
    n = {}
    for atom in m.GetAtoms():
        symbol = {2: 'D', 3: 'T'}.get(atom.GetIsotope(), 'H') if atom.GetAtomicNum() == 1 else atom.GetSymbol()
        n[symbol] = n.get(symbol, 0) + 1
    return n, Chem.GetFormalCharge(mol)


def species_errors(m, known):
    """What is wrong with one species the model listed, in words for the model."""
    out = []
    if m.get('kind') not in KINDS:
        out.append(f'kind must be one of {", ".join(KINDS)}')
    bad = [b for b in m.get('blocks') or [] if b not in known]
    if bad or not m.get('blocks'):
        out.append(f'blocks must be ids from the BLOCKS given ({", ".join(bad) or "none given"})')
    mol = parse(m.get('smiles'))
    if mol is None:
        return out + [f'SMILES {m.get("smiles")!r} does not parse']
    if m.get('formula'):
        want, got = book_formula(m['formula']), structure_formula(mol)
        if want != got:
            out.append(f'the SMILES is {CalcMolFormula(mol)} (charge {got[1]}) but the book formula '
                       f'{m["formula"]} has {want[0]} (charge {want[1]}); fix whichever is wrong')
    return out


def errors(result, known):
    return [f'molecule {i} ({m.get("name", "?")}): {e}' for i, m in enumerate(result['molecules'], 1)
            for e in species_errors(m, known)]


def keep_good(result, known, rejected):
    """The last attempt: species still wrong leave the list (with why) so one of them cannot stop a chapter."""
    kept = []
    for m in result['molecules']:
        problems = species_errors(m, known)
        if problems:
            rejected.append({'name': m.get('name'), 'formula': m.get('formula'), 'smiles': m.get('smiles'),
                             'problems': problems})
        else:
            kept.append(m)
    result['molecules'] = kept
    return result


def block_lines(digest):
    for b in digest['blocks']:
        items = ' '.join(json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x for x in b.get('items') or [])
        yield f'{b["id"]} [{b["type"]}] {b.get("title") or ""}: {b.get("text") or ""} {items}'.strip()


def chunks(lines):
    out, size = [[]], 0
    for line in lines:
        if size + len(line) > CHUNK and out[-1]:
            out.append([])
            size = 0
        out[-1].append(line)
        size += len(line)
    return out


def client(folder):
    registry = models.Registry(SCIVID_DATA, dict)
    connection = registry.load()['connections'][MODEL]
    snapshot = {'steps': {'molecules': MODEL}, 'connections': {MODEL: connection}}
    return models.client_for(snapshot, 'molecules', folder, SCIVID_DATA)


def chapter(code):
    folder = OUT / code
    digest = json.loads((folder / 'digest.json').read_text())
    s = digest['source']
    known = {b['id'] for b in digest['blocks']}
    pages = {b['id']: b.get('pages') or [] for b in digest['blocks']}
    llm = client(folder)
    found, rejected = [], []
    for n, part in enumerate(chunks(list(block_lines(digest))), 1):
        prompt = PROMPT.format(cls=s['class'], book=s.get('book_title', ''), no=s['chapter'], title=s['title'],
                               schema=SCHEMA, blocks='\n'.join(part))
        tries = []

        def validate(result, part_known={line.split(' ', 1)[0] for line in part}):
            tries.append(1)
            if len(tries) == ATTEMPTS:
                return keep_good(result, part_known, rejected)
            problems = errors(result, part_known)
            if problems:
                raise ValueError('; '.join(problems[:25]))
            return result
        result = llm.call(f'molecules-{n}', prompt, max_tokens=32000, validate=validate, attempts=ATTEMPTS)
        found += result['molecules']
        print(f'{code} part {n}: {len(result["molecules"])} species', flush=True)
    # one entry per structure, with every name and block the parts gave it
    merged = {}
    for m in found:
        key = Chem.MolToSmiles(parse(m['smiles']))
        if key in merged:
            e = merged[key]
            e['aliases'] = sorted({*e['aliases'], *m.get('aliases', []), m['name']} - {e['name']})
            e['blocks'] = sorted({*e['blocks'], *m['blocks']}, key=lambda b: int(b[1:]) if b[1:].isdigit() else 0)
            e['formula'] = e['formula'] or m.get('formula', '')
        else:
            merged[key] = {**m, 'aliases': sorted(set(m.get('aliases', [])) - {m['name']})}
    molecules = [{**m, 'pages': sorted({p for b in m['blocks'] for p in pages.get(b, [])})} for m in merged.values()]
    out = {'chapter': code, 'class': s['class'], 'title': s['title'], 'model': MODEL, 'molecules': molecules,
           'rejected': rejected}
    (folder / 'molecules.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f'{code}: {len(molecules)} species, {len(rejected)} set aside -> {folder / "molecules.json"}', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('chapters', nargs='+')
    for code in ap.parse_args().chapters:
        chapter(code)


if __name__ == '__main__':
    main()
