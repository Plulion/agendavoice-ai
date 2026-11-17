def normalize_rut(value: str) -> str:
    return value.replace(".", "").replace("-", "").replace(" ", "").upper()

def is_valid_chilean_rut(value: str) -> bool:
    clean = normalize_rut(value)
    if len(clean) < 2 or not clean[:-1].isdigit() or clean[-1] not in "0123456789K":
        return False
    total = 0
    factor = 2
    for digit in reversed(clean[:-1]):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    expected = "0" if remainder == 11 else "K" if remainder == 10 else str(remainder)
    return clean[-1] == expected
