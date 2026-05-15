from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.inline import main_menu_keyboard


def _get_menu_data(telegram_id):
    from users.models import Player
    try:
        player = Player.objects.get(telegram_id=telegram_id)
    except Player.DoesNotExist:
        player = Player.objects.create(telegram_id=telegram_id)
    text = (
        f"🎮 *Bingo2Bingo* — Main Menu\n\n"
        f"👤 *{player.first_name or player.username}*\n"
        f"🪙 Balance: *{player.coins} coins*\n"
        f"⭐ Level: *{player.level}* | XP: *{player.xp}*\n"
        f"🏆 Wins: *{player.wins}* | ❌ Losses: *{player.losses}*\n\n"
        f"👇 Choose an option:"
    )
    return text


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    text = await sync_to_async(_get_menu_data)(user.id)

    await query.edit_message_text(
        text,
        reply_markup=main_menu_keyboard(user.id),
        parse_mode='Markdown'
    )
