from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.inline import wallet_keyboard


def _get_wallet_data(telegram_id):
    from users.models import Player
    from wallets.models import Transaction
    player = Player.objects.get(telegram_id=telegram_id)
    txns = Transaction.objects.filter(player=player).order_by('-created_at')[:10]
    txn_text = ''
    for tx in txns:
        sign = '+' if tx.amount > 0 else ''
        txn_text += f"{sign}{tx.amount}💰 — {tx.get_transaction_type_display()}\n"
    text = (
        f"👛 *My Wallet*\n\n"
        f"🪙 Balance: *{player.coins} coins*\n"
        f"💎 Level: *{player.level}* | ⭐ XP: *{player.xp}*\n\n"
        f"📊 *Recent Transactions:*\n"
        f"{txn_text if txn_text else 'No transactions yet.'}"
    )
    return text


async def wallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    text = await sync_to_async(_get_wallet_data)(user.id)

    await query.edit_message_text(
        text, reply_markup=wallet_keyboard(), parse_mode='Markdown'
    )
