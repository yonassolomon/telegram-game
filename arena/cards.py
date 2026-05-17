import random


def generate_card_by_number(card_number):
    if not (1 <= card_number <= 300):
        raise ValueError('Card number must be 1-300')

    rng = random.Random(card_number * 7919 + 104729)
    cols = [
        sorted(rng.sample(range(1, 16), 5)),
        sorted(rng.sample(range(16, 31), 5)),
        sorted(rng.sample(range(31, 46), 5)),
        sorted(rng.sample(range(46, 61), 5)),
        sorted(rng.sample(range(61, 76), 5)),
    ]
    numbers = []
    for row in range(5):
        for col in range(5):
            numbers.append(cols[col][row])
    numbers[12] = 0
    return numbers


def format_card_grid(numbers, marked_set=None):
    if marked_set is None:
        marked_set = set()
    rows = []
    for r in range(5):
        cells = []
        for c in range(5):
            idx = r * 5 + c
            val = numbers[idx]
            if idx == 12:
                cells.append({'num': 0, 'display': '⭐', 'free': True, 'marked': True})
            else:
                cells.append({
                    'num': val,
                    'display': f'{val:02d}',
                    'free': False,
                    'marked': val in marked_set
                })
        rows.append(cells)
    return rows
