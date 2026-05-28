from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.inline import main_menu_keyboard


def _handle_start(telegram_id, username, first_name, args):
    from users.models import Player
    from referrals.models import Referral

    try:
        player = Player.objects.get(telegram_id=telegram_id)
        created = False
    except Player.DoesNotExist:
        player = Player.objects.create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name
        )
        created = True

    if not created and username:
        if player.username != username or player.first_name != first_name:
            player.username = username
            player.first_name = first_name
            player.save(update_fields=['username', 'first_name'])

    if args and created:
        referral_code = args[0]
        try:
            inviter = Player.objects.get(referral_code=referral_code)
            if inviter.id != player.id:
                _, ref_created = Referral.objects.get_or_create(inviter=inviter, invited=player)
                if ref_created:
                    inviter.coins += 1
                    inviter.save(update_fields=['coins'])
                    from wallets.models import Transaction
                    Transaction.objects.create(
                        player=inviter, amount=1,
                        transaction_type='referral_bonus',
                        description=f'Referral join bonus for inviting {player.first_name}'
                    )
        except Player.DoesNotExist:
            pass

    if created:
        text = (
            f"🎉 *Welcome to Bingo2Bingo, {player.first_name or player.username}!*\n\n"
            f"🪙 You received *10 starter coins*!\n"
            f"🎮 Play bingo, win big, and climb the leaderboard!\n\n"
            f"👇 Choose an option below:"
        )
    else:
        text = (
            f"👋 *Welcome back, {player.first_name or player.username}!*\n\n"
            f"🪙 Balance: *{player.coins} coins*\n"
            f"🏆 Wins: *{player.wins}* | ❌ Losses: *{player.losses}*\n\n"
            f"👇 Choose an option below:"
        )
    return text


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    text = await sync_to_async(_handle_start)(
        user.id,
        user.username or '',
        user.first_name or '',
        args or []
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(user.id),
        parse_mode='Markdown'
    )
