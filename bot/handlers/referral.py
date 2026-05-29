from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.inline import referral_keyboard


def _get_bot_username():
    from django.conf import settings
    return getattr(settings, 'BOT_USERNAME', 'Bingo2BingoBot')


def _get_referral_data(telegram_id):
    from users.models import Player
    from referrals.models import Referral
    player = Player.objects.get(telegram_id=telegram_id)
    invited_count = Referral.objects.filter(inviter=player).count()
    bot_username = _get_bot_username()
    return player.referral_code, invited_count, bot_username


async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    code, count, bot_username = await sync_to_async(_get_referral_data)(user.id)
    link = f"https://t.me/{bot_username}?start={code}"

    text = (
        f"👥 *Invite Friends*\n\n"
        f"Share your link and earn rewards!\n\n"
        f"🔗 Your link:\n`{link}`\n\n"
        f"👤 Friends invited: *{count}*\n"
        f"🎁 *+1 coin* when friend joins!\n"
        f"💰 *+3 coins* when friend deposits (10+ coins)!\n\n"
        f"📋 Tap below to copy your link."
    )
    await query.edit_message_text(
        text, reply_markup=referral_keyboard(code), parse_mode='Markdown'
    )


async def copy_ref_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    code = query.data.replace('copyref_', '')
    from django.conf import settings
    bot_username = getattr(settings, 'BOT_USERNAME', 'Bingo2BingoBot')
    link = f"https://t.me/{bot_username}?start={code}"
    await query.answer(f"Your link: {link}", show_alert=True)
