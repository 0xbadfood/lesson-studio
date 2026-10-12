"""Spoken-form normalizer: narration becomes exactly the words a listener hears, before TTS, MFA and the audit.

No digits, symbols or abbreviations survive: "9.8 m/s²" -> "nine point eight metres per second squared",
"₹1,500" -> "one thousand five hundred rupees", "1890" -> "eighteen ninety", "θ ≈ 30°" -> "theta is approximately
thirty degrees". The narration and the cue phrases are normalized the same way, so cues still match the words.
Every rule is context-free and idempotent (normalizing twice changes nothing).
"""
import re

ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve',
        'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']
TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
SCALES = [(10 ** 12, 'trillion'), (10 ** 9, 'billion'), (10 ** 6, 'million'), (1000, 'thousand')]
ORDINAL = {'one': 'first', 'two': 'second', 'three': 'third', 'five': 'fifth', 'eight': 'eighth', 'nine': 'ninth',
           'twelve': 'twelfth'}
DENOMINATOR = {2: ('half', 'halves'), 4: ('quarter', 'quarters')}


def integer(n):
    """Cardinal words for a non-negative integer."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ('-' + ONES[n % 10] if n % 10 else '')
    if n < 1000:
        rest = n % 100
        return ONES[n // 100] + ' hundred' + (' and ' + integer(rest) if rest else '')
    for value, name in SCALES:
        if n >= value:
            head, rest = divmod(n, value)
            tail = '' if not rest else (' and ' if rest < 100 else ' ') + integer(rest)
            return integer(head) + ' ' + name + tail
    raise ValueError(n)


def ordinal(n):
    words = integer(n)
    head, sep, last = words.rpartition('-' if '-' in words.split()[-1] else ' ')
    if last in ORDINAL:
        last = ORDINAL[last]
    elif last.endswith('y'):
        last = last[:-1] + 'ieth'
    else:
        last += 'th'
    return head + sep + last


def plural(words):
    return words[:-1] + 'ies' if words.endswith('y') else words + 's'


def year(n):
    """Years the way they are said: 1890 'eighteen ninety', 1905 'nineteen oh five', 2005 'two thousand five'."""
    if 2000 <= n <= 2009:
        return 'two thousand' + (' ' + integer(n % 10) if n % 10 else '')
    head, tail = divmod(n, 100)
    if tail == 0:
        return integer(head) + ' hundred'
    return integer(head) + ' ' + ('oh ' + integer(tail) if tail < 10 else integer(tail))


def number(token):
    """'1,500' / '6.283' / '0.5' -> words."""
    whole, _, frac = token.replace(',', '').partition('.')
    words = integer(int(whole or 0))
    if frac:
        words += ' point ' + ' '.join(ONES[int(d)] for d in frac)
    return words


def fraction(a, b):
    if b in DENOMINATOR:
        return integer(a) + ' ' + DENOMINATOR[b][a != 1]
    if 3 <= b <= 12 and a < b:
        name = ordinal(b)
        return integer(a) + ' ' + (name if a == 1 else name + 's')
    return integer(a) + ' over ' + integer(b)


GREEK = {'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta', 'Δ': 'delta', 'ε': 'epsilon', 'θ': 'theta',
         'λ': 'lambda', 'μ': 'mu', 'π': 'pi', 'ρ': 'rho', 'σ': 'sigma', 'Σ': 'sigma', 'τ': 'tau', 'φ': 'phi',
         'ω': 'omega', 'Ω': 'omega', 'η': 'eta', 'ν': 'nu', 'χ': 'chi', 'ψ': 'psi'}
SYMBOLS = [('≠', ' is not equal to '), ('≈', ' is approximately '), ('≤', ' is at most '), ('≥', ' is at least '),
           ('±', ' plus or minus '), ('∞', ' infinity '), ('∝', ' is proportional to '), ('→', ' becomes '),
           ('√', ' the square root of '), ('×', ' times '), ('·', ' times '), ('÷', ' divided by '), ('=', ' equals '),
           ('+', ' plus '), ('−', ' minus '), ('<', ' is less than '), ('>', ' is greater than '), ('&', ' and '),
           ('@', ' at '), ('%', ' percent'), ('*', ' times '), ('#', ' number '), ('~', ' about ')]
SUPERSCRIPT = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁻', '0123456789-')
UNITS = [  # after a number (most specific first); a few multi-letter units also stand alone after "in"/"or"
    (r'm/s\^?2|m/s²|m s\^?-2|m s⁻²', 'metres per second squared'), (r'km/h|km/hr|kmph', 'kilometres per hour'),
    (r'cm/s', 'centimetres per second'), (r'm/s', 'metres per second'), (r'rad/s', 'radians per second'),
    (r'kg/m\^?3|kg/m³', 'kilograms per cubic metre'), (r'g/cm\^?3|g/cm³', 'grams per cubic centimetre'),
    (r'km²|km\^2', 'square kilometres'), (r'm²|m\^2', 'square metres'), (r'cm²|cm\^2', 'square centimetres'),
    (r'm³|m\^3', 'cubic metres'), (r'cm³|cm\^3', 'cubic centimetres'),
    (r'kWh', 'kilowatt hours'), (r'kW', 'kilowatts'), (r'MW', 'megawatts'), (r'kJ', 'kilojoules'),
    (r'kPa', 'kilopascals'), (r'Pa', 'pascals'), (r'kg', 'kilograms'), (r'mg', 'milligrams'), (r'km', 'kilometres'),
    (r'cm', 'centimetres'), (r'mm', 'millimetres'), (r'nm', 'nanometres'), (r'μm|µm', 'micrometres'),
    (r'mL|ml', 'millilitres'), (r'L', 'litres'), (r'°C', 'degrees Celsius'), (r'°F', 'degrees Fahrenheit'),
    (r'°', 'degrees'), (r'K', 'kelvin'), (r'mol', 'moles'), (r'Hz', 'hertz'), (r'kHz', 'kilohertz'),
    (r'ms', 'milliseconds'), (r'min', 'minutes'), (r'hr|h', 'hours'), (r'N', 'newtons'), (r'J', 'joules'),
    (r'W', 'watts'), (r'V', 'volts'), (r'A', 'amperes'), (r'Ω', 'ohms'), (r'm', 'metres'), (r's', 'seconds'),
    (r'g', 'grams')]
SINGULAR = {'metres': 'metre', 'kilometres': 'kilometre', 'centimetres': 'centimetre', 'millimetres': 'millimetre',
            'kilograms': 'kilogram', 'grams': 'gram', 'seconds': 'second', 'minutes': 'minute', 'hours': 'hour',
            'newtons': 'newton', 'joules': 'joule', 'watts': 'watt', 'volts': 'volt', 'litres': 'litre',
            'degrees': 'degree', 'rupees': 'rupee', 'dollars': 'dollar', 'euros': 'euro', 'pounds': 'pound',
            'moles': 'mole', 'pascals': 'pascal', 'ohms': 'ohm', 'amperes': 'ampere', 'radians': 'radian'}
ABBREVIATIONS = [(r'\be\.g\.', 'for example'), (r'\bi\.e\.', 'that is'), (r'\betc\.', 'et cetera'),
                 (r'\bvs\.?(?=\s)', 'versus'), (r'\bapprox\.', 'approximately'), (r'\bDr\.', 'Doctor'),
                 (r'\bMr\.', 'Mister'), (r'\bMrs\.', 'Missus'), (r'\bNo\.(?=\s*\d)', 'number'),
                 (r'\bRs\.?(?=\s*\d)', '₹'), (r'\bINR(?=\s*\d)', '₹')]
NUMBER_WORDS = '|'.join(ONES + TENS[2:] + ['hundred', 'thousand', 'million', 'billion', 'half'])
NUM = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'


def _num(m):
    token = m.group(0)
    if re.fullmatch(r'\d{4}', token) and 1100 <= int(token) <= 2099:
        return year(int(token))
    return number(token)


def spoken(text):
    """Return the narration as the exact words a listener hears."""
    if not text:
        return text
    t = text.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '…': '...', '–': '-', '—': ', ',
                                      ' ': ' ', ' ': ' '}))
    for pattern, words in ABBREVIATIONS:
        t = re.sub(pattern, words, t)
    # money: ₹1,500 / $2.5 million -> "1,500 rupees" (the number becomes words below)
    for sign, name in (('₹', 'rupees'), ('$', 'dollars'), ('€', 'euros'), ('£', 'pounds')):
        t = re.sub(re.escape(sign) + r'\s*(' + NUM + r')(\s+(?:thousand|lakh|crore|million|billion))?',
                   lambda m: m.group(1) + (m.group(2) or '') + ' ' + name, t)
    # exponents before units/superscripts are flattened: x² stays "squared", 10⁸ / 10^8 -> "to the power"
    t = re.sub(r'([⁰¹⁴⁵⁶⁷⁸⁹⁻][⁰¹²³⁴⁵⁶⁷⁸⁹⁻]*|[²³][⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)', lambda m: '^' + m.group(1).translate(SUPERSCRIPT), t)
    for pattern, words in UNITS:
        gap = r'\s+' if pattern == 's' else r'\s*'           # "the 1600s" stays a decade
        t = re.sub(r'(?<=\d)' + gap + '(?:' + pattern + r')(?![\w/²³^])', ' ' + words, t)
        if len(pattern) > 2 and '/' in pattern:
            t = re.sub(r'(?<![\w/])(?:' + pattern + r')(?![\w/²³^])', words, t)
        t = re.sub(r'(?<=\b(?:in|or) )(?:' + pattern + r')(?=[\s,;.)]|$)', words, t)
    t = t.replace('²', ' squared').replace('³', ' cubed')
    t = re.sub(r'\^\s*\(?\s*2\s*\)?(?!\d)', ' squared', t)
    t = re.sub(r'\^\s*\(?\s*3\s*\)?(?!\d)', ' cubed', t)
    t = re.sub(r'\^\s*\(?\s*(-?)\s*(\d+)(?:\s*\))?', lambda m: ' to the power ' + ('minus ' if m.group(1) else '') + m.group(2), t)
    for letter, name in GREEK.items():
        t = re.sub(r'(?<=[A-Za-z0-9])' + letter, ' ' + name, t).replace(letter, name)
    # number shapes that need words other than plain cardinals
    t = re.sub(r'\b(\d{2,4})s\b', lambda m: plural(year(int(m.group(1))) if len(m.group(1)) == 4 else integer(int(m.group(1))))
               if not m.group(1).endswith('00') else integer(int(m.group(1)) // 100) + ' hundreds', t)
    # "exp" and "sqrt" are written shorthand a voice cannot read (VibeVoice said "XP-tahons" for "exp")
    t = re.sub(r'\bexp\b\s*(?:of\b\s*)?', 'e to the power of ', t)
    t = re.sub(r'\bsqrt\b\s*(?:of\b\s*)?', 'the square root of ', t)
    for name, said in (('sin', 'sine'), ('cos', 'cosine'), ('tan', 'tangent of'), ('ln', 'natural log of')):
        t = re.sub(r'\b' + name + r'(?=\s*[(A-Za-z0-9θφαβπ])(?!\w)', said, t)
    t = re.sub(r'\b(\d+)(st|nd|rd|th)\b', lambda m: ordinal(int(m.group(1))), t)
    t = re.sub(r'(?<![\d.,/])(\d+)\s*/\s*(\d+)(?![\d.,/])', lambda m: fraction(int(m.group(1)), int(m.group(2))), t)
    t = re.sub(NUM + r'(?:-' + NUM + r'){2,}', lambda m: m.group(0).replace('-', ' '), t)  # a 3-4-5 triangle
    t = re.sub(r'(' + NUM + r')\s*-\s*(?=' + NUM + r')', r'\1 to ', t)                  # 5-10 -> 5 to 10
    t = re.sub(r'(?<![\w)])-\s?(?=\d)', 'minus ', t)                                   # -5 -> minus 5
    t = re.sub(r'(?<=[(\[=])\s*-\s?(?=[A-Za-zα-ω])', 'minus ', t)                       # (-t -> (minus t
    t = re.sub(r'(?<=\d):(?=\d)', ' to ', t)                                            # 3:1 -> 3 to 1
    t = re.sub(r'\b(\d)D\b', r'\1-D', t)                                               # 3D -> three-D
    t = re.sub(r'(\d)([A-Za-z]{1,4})\b', lambda m: m.group(1) + ' ' + ' '.join(m.group(2)), t)  # 2ab -> 2 a b
    t = re.sub(NUM, _num, t)
    for word, name in SYMBOLS:
        t = t.replace(word, name)
    # "/" left after units is maths ("v squared/r" -> "over") unless it joins two words ("cost/day" -> "per")
    t = re.sub(r'(\w+)\s*/\s*(\w+)', lambda m: m.group(1) + (' over ' if min(len(m.group(1)), len(m.group(2))) == 1
                                                                 else ' per ') + m.group(2), t)
    # "one metres" -> "one metre" (and "minus one", "point one" keep the plural, as in speech)
    t = re.sub(r'(?<!point )(?<!minus )\bone (' + '|'.join(SINGULAR) + r')\b', lambda m: 'one ' + SINGULAR[m.group(1)], t)
    # Whisper writes "two n" as "2n" and "nonzero" as "non-zero": say both unambiguously
    # and writes "two a b" as "2ab": a number word before letters is a product, said with "times"
    t = re.sub(r'\b(' + NUMBER_WORDS + r')((?: [A-Za-z]\b(?![\'])){2,})', lambda m: m.group(1) + ''.join(
        ' times ' + x for x in m.group(2).split()), t)
    t = re.sub(r'\b(' + NUMBER_WORDS + r') ([b-hj-zB-HJ-Z])\b(?![\'])', r'\1 times \2', t)
    t = re.sub(r'\bnon(zero|negative|positive)\b', r'non-\1', t, flags=re.I)
    t = re.sub(r'\b((?:\w+ ){0,4}\w+), or \1\b', r'\1', t)        # "metres per second, or m/s" after expansion
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return re.sub(r'\s+([,.;:?!])', r'\1', t).strip()


def leftovers(text):
    """Characters a listener cannot hear as written (digits and symbols) still present after normalizing."""
    return sorted(set(re.findall(r'[0-9^_=<>+×÷%$₹€£#*/\\|{}\[\]~@&]', text)))
