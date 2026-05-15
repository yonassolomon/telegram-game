from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("🎮 Play Bingo", callback_data="play")],
        [
            InlineKeyboardButton("👛 Wallet", callback_data="wallet"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
        ],
        [
            InlineKeyboardButton("👥 Invite Friends", callback_data="referral"),
            InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily"),
        ],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    return InlineKeyboardMarkup(buttons)


def wallet_keyboard():
    buttons = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def play_menu_keyboard(rooms):
    buttons = []
    for room in rooms:
        status_emoji = {'waiting': '🟢', 'active': '🔴', 'finished': '⚫'}
        emoji = status_emoji.get(room.status, '⚪')
        count = getattr(room, '_player_count', 0)
        label = f"{emoji} Room {room.room_code} | {count}/{room.max_players} | {room.entry_fee}💰"
        buttons.append([InlineKeyboardButton(label, callback_data=f"join_{room.room_code}")])
    buttons.append([InlineKeyboardButton("➕ Create Room", callback_data="create_room")])
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="play")])
    buttons.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def create_room_keyboard():
    buttons = [
        [
            InlineKeyboardButton("50💰 Entry", callback_data="roomfee_50"),
            InlineKeyboardButton("100💰 Entry", callback_data="roomfee_100"),
        ],
        [
            InlineKeyboardButton("200💰 Entry", callback_data="roomfee_200"),
            InlineKeyboardButton("500💰 Entry", callback_data="roomfee_500"),
        ],
        [
            InlineKeyboardButton("2 Players", callback_data="roomsize_2"),
            InlineKeyboardButton("4 Players", callback_data="roomsize_4"),
        ],
        [
            InlineKeyboardButton("6 Players", callback_data="roomsize_6"),
            InlineKeyboardButton("10 Players", callback_data="roomsize_10"),
        ],
        [InlineKeyboardButton("🎯 Create Now!", callback_data="confirm_create")],
        [InlineKeyboardButton("⬅️ Back", callback_data="play")],
    ]
    return InlineKeyboardMarkup(buttons)


def room_waiting_keyboard(room):
    buttons = []
    if room.status == 'waiting':
        buttons.append([InlineKeyboardButton("🚀 Start Game", callback_data=f"start_{room.room_code}")])
    buttons.append([InlineKeyboardButton("🚪 Leave Room", callback_data=f"leave_{room.room_code}")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="play")])
    return InlineKeyboardMarkup(buttons)


def leaderboard_keyboard(players, page=0):
    buttons = []
    for i, player in enumerate(players, start=1 + page * 5):
        medals = {1: '🥇', 2: '🥈', 3: '🥉'}
        medal = medals.get(i, f'{i}.')
        label = f"{medal} {player.username or player.first_name} — {player.coins}💰 | {player.wins}🏆"
        buttons.append([InlineKeyboardButton(label, callback_data=f"profile_{player.telegram_id}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"lb_{page-1}"))
    nav.append(InlineKeyboardButton("⬅️ Menu", callback_data="menu"))
    nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"lb_{page+1}"))
    buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def daily_bonus_keyboard(can_claim, next_claim=''):
    if can_claim:
        buttons = [[InlineKeyboardButton("🎁 Claim Bonus!", callback_data="claim_daily")]]
    else:
        buttons = [[InlineKeyboardButton(f"⏳ Next: {next_claim}", callback_data="noop")]]
    buttons.append([InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def referral_keyboard(referral_code):
    bot_username = "Bingo2BingoBot"
    link = f"https://t.me/{bot_username}?start={referral_code}"
    buttons = [
        [InlineKeyboardButton("📋 Copy Referral Link", callback_data=f"copyref_{referral_code}")],
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def help_keyboard():
    buttons = [
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def game_over_keyboard():
    buttons = [
        [InlineKeyboardButton("🎮 Play Again", callback_data="play")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def noop_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")]])
