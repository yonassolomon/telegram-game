from asgiref.sync import sync_to_async
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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
        player.coins = 30
        player.registration_bonus_claimed = True
        player.save(update_fields=['coins', 'registration_bonus_claimed'])
        text = (
            f"🎉 *Welcome to Bingo2Bingo, {player.first_name or player.username}!*\n\n"
            f"🪙 You received *30 bonus coins*!\n"
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
    return text, created, player.phone_number


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    text, created, phone = await sync_to_async(_handle_start)(
        user.id,
        user.username or '',
        user.first_name or '',
        args or []
    )

    if not phone:
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Share Contact", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
        await update.message.reply_text(
            "📱 *Phone Number Required*\n\n"
            "ስልክ ቁጥር ማስገባት ግዴታ ነው\n"
            "Please share your contact to continue.",
            reply_markup=kb,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=main_menu_keyboard(user.id),
            parse_mode='Markdown'
        )


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact:
        phone = contact.phone_number

        def _save_phone():
            from users.models import Player
            from django.db import transaction as db_transaction
            p = Player.objects.get(telegram_id=update.effective_user.id)

            existing = Player.objects.filter(phone_number=phone).exclude(id=p.id).first()
            if existing:
                return None, None, 'This phone number is already registered with another account'

            with db_transaction.atomic():
                p = Player.objects.select_for_update().get(id=p.id)
                p.phone_number = phone
                if not p.registration_bonus_claimed:
                    p.registration_bonus_claimed = True
                    p.save(update_fields=['phone_number', 'registration_bonus_claimed'])
                else:
                    p.save(update_fields=['phone_number'])
                p.refresh_from_db()
                return p.first_name, p.coins, None

        name, coins, error = await sync_to_async(_save_phone)()

        if error:
            await update.message.reply_text(
                f"⚠️ {error}\n\nPlease use a different phone number.",
            )
            return

        from telegram import ReplyKeyboardRemove
        await update.message.reply_text(
            f"✅ Phone saved: *{phone}*\n\n"
            f"🎉 *Welcome to Bingo2Bingo, {name}!*\n"
            f"🪙 Balance: *{coins} coins*\n"
            f"🎮 Play bingo, win big!\n\n"
            f"👇 Choose an option below:",
            reply_markup=main_menu_keyboard(update.effective_user.id),
            parse_mode='Markdown'
        )
