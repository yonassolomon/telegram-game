from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def _get_leaderboard(page):
    from users.models import Player
    offset = page * 5
    top_players = list(Player.objects.filter(is_banned=False).order_by('-wins')[offset:offset + 5])
    total = Player.objects.filter(is_banned=False).count()
    max_page = (total - 1) // 5 if total > 0 else 0
    lines = []
    for i, p in enumerate(top_players, start=offset + 1):
        medals = {1: '🥇', 2: '🥈', 3: '🥉'}
        medal = medals.get(i, f'{i}.')
        lines.append(f"{medal} *{p.username or p.first_name}* — {p.wins} wins | {p.coins}💰")
    return lines, page, max_page


async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    page = 0
    if query.data and query.data.startswith('lb_'):
        page = int(query.data.split('_')[1])

    lines, page_num, max_page = await sync_to_async(_get_leaderboard)(page)

    text = f"🏆 *Leaderboard* — Page {page_num + 1}/{max_page + 1}\n\n🥇 *Top Winners*\n\n"
    text += "\n".join(lines) if lines else "No players yet."

    nav = []
    if page_num > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"lb_{page_num - 1}"))
    nav.append(InlineKeyboardButton("⬅️ Menu", callback_data="menu"))
    if page_num < max_page:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"lb_{page_num + 1}"))
    kb = InlineKeyboardMarkup([nav])

    await query.edit_message_text(text, reply_markup=kb, parse_mode='Markdown')
