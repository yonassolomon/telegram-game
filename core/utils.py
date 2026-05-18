import random
from asgiref.sync import sync_to_async


def generate_bingo_card():
    cols = [
        random.sample(range(1, 16), 5),
        random.sample(range(16, 31), 5),
        random.sample(range(31, 46), 5),
        random.sample(range(46, 61), 5),
        random.sample(range(61, 76), 5),
    ]
    numbers = []
    for row in range(5):
        for col in range(5):
            numbers.append(cols[col][row])
    numbers[12] = 0
    return numbers


def format_card(numbers, marked):
    marked_set = set(marked)
    header = "🔵🟢🟡🟣🔴\n"
    lines = []
    for row in range(5):
        line = ""
        for col in range(5):
            idx = row * 5 + col
            num = numbers[idx]
            if idx == 12:
                line += "⭐ "
            elif num in marked_set:
                line += "✅ "
            else:
                line += f"{num:02d} "
        lines.append(line.strip())
    return header + "\n".join(lines)


def generate_random_numbers():
    numbers = list(range(1, 76))
    random.shuffle(numbers)
    return numbers


def async_db(func):
    """Decorator to run a synchronous DB function in a thread."""
    async def wrapper(*args, **kwargs):
        return await sync_to_async(func)(*args, **kwargs)
    return wrapper


HOUSE_FEE_PERCENT = 10


def calculate_prize(total_pot):
    fee = int(total_pot * HOUSE_FEE_PERCENT / 100)
    return total_pot - fee, fee
