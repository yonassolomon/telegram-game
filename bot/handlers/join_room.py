from asgiref.sync import sync_to_async
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes
from django.conf import settings


def _join_by_code(telegram_id, room_code):
    from users.models import Player
    from games.models import GameRoom
    try:
        room = GameRoom.objects.get(room_code=room_code.upper(), status='waiting', room_type='private')
    except GameRoom.DoesNotExist:
        return None, 'Private room not found or already started'
    return room.room_code, None


async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔐 *Join Private Room*\n\n"
            "Use: `/join CODE`\n"
            "Example: `/join X7K92A`\n\n"
            "Get the code from the room creator.",
            parse_mode='Markdown'
        )
        return

    room_code = args[0].strip().upper()
    user = update.effective_user

    result, error = await sync_to_async(_join_by_code)(user.id, room_code)
    if error:
        await update.message.reply_text(f"❌ {error}")
        return

    webapp_url = settings.WEBAPP_URL if hasattr(settings, 'WEBAPP_URL') else ''
    if webapp_url and '127.0.0.1' not in webapp_url:
        await update.message.reply_text(
            f"✅ Room *{result}* found!\n👇 Open to join:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎮 Join Room", web_app=WebAppInfo(url=f"{webapp_url}?tg_id={user.id}"))
            ]]),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"✅ Room *{result}* found!\n"
            f"Open the Mini App and enter code `{result}` on the Join page.",
            parse_mode='Markdown'
        )


async def join_private_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔐 *Join Private Room*\n\n"
        "Use the `/join CODE` command or open the Mini App:\n"
        "🏠 Play Bingo → 🔐 Join by Code\n\n"
        "Enter the room code shared by your friend.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Back", callback_data="play")
        ]]),
        parse_mode='Markdown'
    )
