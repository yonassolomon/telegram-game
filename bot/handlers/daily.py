from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from django.utils import timezone
from bot.keyboards.inline import daily_bonus_keyboard

DAILY_REWARD = 100


def _get_daily_data(telegram_id):
    from users.models import Player
    from wallets.models import Transaction
    player = Player.objects.get(telegram_id=telegram_id)
    can_claim = player.can_claim_daily()
    next_str = ''
    if not can_claim and player.last_daily_bonus:
        remaining = 86400 - (timezone.now() - player.last_daily_bonus).total_seconds()
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        next_str = f'{hours}h {mins}m'
    return player.coins, can_claim, next_str


def _claim_daily(telegram_id):
    from users.models import Player
    from wallets.models import Transaction
    player = Player.objects.select_for_update().get(telegram_id=telegram_id)
    if not player.can_claim_daily():
        remaining = 86400 - (timezone.now() - player.last_daily_bonus).total_seconds()
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        return None, f'{hours}h {mins}m'
    player.coins += DAILY_REWARD
    player.xp += 25
    player.last_daily_bonus = timezone.now()
    player.save(update_fields=['coins', 'xp', 'last_daily_bonus'])
    Transaction.objects.create(
        player=player, amount=DAILY_REWARD,
        transaction_type='daily_bonus', description='Daily bonus claimed'
    )
    return player.coins, None


async def daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    _, can_claim, next_str = await sync_to_async(_get_daily_data)(user.id)

    text = f"🎁 *Daily Bonus*\n\nClaim *{DAILY_REWARD} coins* every 24 hours!\n"
    if can_claim:
        text += "\n✅ You can claim now!"
    else:
        text += f"\n⏳ Next claim in: *{next_str}*"

    await query.edit_message_text(
        text, reply_markup=daily_bonus_keyboard(can_claim, next_str), parse_mode='Markdown'
    )


async def claim_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    new_balance, error = await sync_to_async(_claim_daily)(user.id)

    if error:
        await query.answer(f'Next claim in {error}', show_alert=True)
        return

    text = (
        f"🎁 *Daily Bonus Claimed!*\n\n"
        f"➕ *{DAILY_REWARD} coins* added to your wallet!\n"
        f"💎 New balance: *{new_balance} coins*\n\n"
        f"⏳ Come back in 24 hours for more!"
    )
    await query.edit_message_text(
        text, reply_markup=daily_bonus_keyboard(False, '23h 59m'), parse_mode='Markdown'
    )
