# utils/card_utils.py
import re

def extract_card_from_text(text):
    if not text:
        return None
    text = text.strip()
    parts = text.split('|')
    if len(parts) >= 4:
        if re.match(r'^\d{13,19}$', parts[0].strip()):
            mm = parts[1].strip().zfill(2)
            yy = parts[2].strip()
            if len(yy) == 4:
                yy = yy[-2:]
            cvc = parts[3].strip()
            if re.match(r'^\d{3,4}$', cvc):
                return f"{parts[0].strip()}|{mm}|{yy}|{cvc}"
    patterns = [
        r'(\d{13,19})\s*[|\-]\s*(\d{1,2})[/](\d{2,4})\s*[|\-]\s*(\d{3,4})',
        r'(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4})\s*[|\-]\s*(\d{1,2})[/](\d{2,4})\s*[|\-]\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})[/](\d{2,4})\s+(\d{3,4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            card_num = re.sub(r'[-\s]', '', match.group(1))
            mm = match.group(2).zfill(2)
            yy = match.group(3)
            if len(yy) == 4:
                yy = yy[-2:]
            cvc = match.group(4)
            return f"{card_num}|{mm}|{yy}|{cvc}"
    return None

def extract_cards_from_text(text):
    cards = []
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line:
            card = extract_card_from_text(line)
            if card:
                cards.append(card)
    return cards

def validate_card_format(card):
    parts = card.split('|')
    if len(parts) != 4:
        return False
    card_num, mm, yy, cvc = parts
    if not re.match(r'^\d{13,19}$', card_num):
        return False
    if not re.match(r'^\d{2}$', mm) or int(mm) < 1 or int(mm) > 12:
        return False
    if not re.match(r'^\d{2}$', yy):
        return False
    if not re.match(r'^\d{3,4}$', cvc):
        return False
    return True
