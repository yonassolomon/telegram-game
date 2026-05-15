from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.inline import play_menu_keyboard, create_room_keyboard, room_waiting_keyboard, main_menu_keyboard
from django.db import transaction as db_transaction, models
from core.utils import generate_bingo_card


def _ensure_player(telegram_id, username, first_name):
    from users.models import Player
    try:
        return Player.objects.get(telegram_id=telegram_id)
    except Player.DoesNotExist:
        return Player.objects.create(telegram_id=telegram_id, username=username, first_name=first_name)


def _get_waiting_rooms():
    from games.models import GameRoom
    from django.db.models import Count
    return list(
        GameRoom.objects.filter(status='waiting')
        .annotate(active_players=Count('bingo_cards'))
        .order_by('-created_at')[:10]
    )


def _create_room_sync(telegram_id, fee, size):
    from users.models import Player
    from games.models import GameRoom, BingoCard
    from wallets.models import Transaction

    with db_transaction.atomic():
        player = Player.objects.select_for_update().get(telegram_id=telegram_id)
        if player.coins < fee:
            return None, f'Not enough coins! Need {fee}, have {player.coins}'
        player.coins = models.F('coins') - fee
        player.save(update_fields=['coins'])
        room = GameRoom.objects.create(
            room_type='public', entry_fee=fee,
            max_players=size, prize_pool=fee,
        )
        BingoCard.objects.create(player=player, game_room=room, numbers=generate_bingo_card())
    Transaction.objects.create(
        player=player, amount=-fee,
        transaction_type='game_entry', description=f'Created room {room.room_code}'
    )
    return room, None


def _join_room_sync(telegram_id, room_code):
    from users.models import Player
    from games.models import GameRoom, BingoCard
    from wallets.models import Transaction

    try:
        room = GameRoom.objects.get(room_code=room_code, status='waiting')
    except GameRoom.DoesNotExist:
        return None, 'Room not available!'

    current_count = room.bingo_cards.count()
    if current_count >= room.max_players:
        return None, 'Room is full!'
    if BingoCard.objects.filter(player__telegram_id=telegram_id, game_room=room).exists():
        return None, 'You already joined this room!'

    with db_transaction.atomic():
        player = Player.objects.select_for_update().get(telegram_id=telegram_id)
        if player.coins < room.entry_fee:
            return None, f'Not enough coins! Need {room.entry_fee}'
        player.coins = models.F('coins') - room.entry_fee
        player.save(update_fields=['coins'])
        BingoCard.objects.create(player=player, game_room=room, numbers=generate_bingo_card())
        room.prize_pool = models.F('prize_pool') + room.entry_fee
        room.save(update_fields=['prize_pool'])

    new_count = current_count + 1

    Transaction.objects.create(
        player=player, amount=-room.entry_fee,
        transaction_type='game_entry', description=f'Joined room {room_code}'
    )
    return {
        'room_code': room.room_code,
        'entry_fee': room.entry_fee,
        'max_players': room.max_players,
        'prize_pool': room.prize_pool,
        'player_count': new_count,
    }, None


def _leave_room_sync(telegram_id, room_code):
    from users.models import Player
    from games.models import BingoCard
    from wallets.models import Transaction

    card = BingoCard.objects.select_related('game_room').get(
        player__telegram_id=telegram_id,
        game_room__room_code=room_code,
        game_room__status='waiting'
    )
    room = card.game_room
    fee = room.entry_fee

    with db_transaction.atomic():
        player = Player.objects.select_for_update().get(telegram_id=telegram_id)
        player.coins = models.F('coins') + fee
        player.save(update_fields=['coins'])
        room.prize_pool = models.F('prize_pool') - fee
        room.save(update_fields=['prize_pool'])
        card.delete()

    Transaction.objects.create(
        player=player, amount=fee,
        transaction_type='deposit', description=f'Refund from leaving room {room_code}'
    )
    return fee


async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await sync_to_async(_ensure_player)(user.id, user.username or '', user.first_name or '')
    rooms = await sync_to_async(_get_waiting_rooms)()

    if not rooms:
        text = "🎮 *Play Bingo*\n\n📭 No active rooms right now.\n➕ Create a new room and invite others!"
    else:
        text = "🎮 *Play Bingo*\n\n🟢 Available rooms:\nSelect a room to join, or create your own!\n"

    await update.message.reply_text(text, reply_markup=play_menu_keyboard(rooms, user.id), parse_mode='Markdown')


async def play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    rooms = await sync_to_async(_get_waiting_rooms)()

    if not rooms:
        text = "🎮 *Play Bingo*\n\n📭 No active rooms right now.\n➕ Create a new room and invite others!"
    else:
        text = "🎮 *Play Bingo*\n\n🟢 Available rooms:\nSelect a room to join, or create your own!\n"

    await query.edit_message_text(text, reply_markup=play_menu_keyboard(rooms, user.id), parse_mode='Markdown')


async def create_room_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "➕ *Create Game Room*\n\n"
        "🎯 Configure your room:\n"
        "💰 Entry Fee | 👥 Max Players\n\n"
        "Current: *50💰* | *4 Players*"
    )
    await query.edit_message_text(text, reply_markup=create_room_keyboard(), parse_mode='Markdown')


async def room_config_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if 'roomfee' not in data and 'roomsize' not in data:
        return

    user_data = context.user_data.setdefault('room_config', {'fee': 50, 'size': 4})
    if data.startswith('roomfee_'):
        user_data['fee'] = int(data.split('_')[1])
    elif data.startswith('roomsize_'):
        user_data['size'] = int(data.split('_')[1])

    fee, size = user_data['fee'], user_data['size']
    text = (
        f"➕ *Create Game Room*\n\n"
        f"🎯 Configure your room:\n"
        f"💰 Entry Fee: *{fee} coins*\n"
        f"👥 Max Players: *{size}*\n\n"
        f"Total Prize Pool: *{fee * size} coins*\n\n"
        f"👇 Tap confirm to create!"
    )
    await query.answer(f'Set: {fee}💰 / {size} players')
    await query.edit_message_text(text, reply_markup=create_room_keyboard(), parse_mode='Markdown')


async def confirm_create_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    config = context.user_data.get('room_config', {'fee': 50, 'size': 4})
    fee, size = config['fee'], config['size']

    room, error = await sync_to_async(_create_room_sync)(user.id, fee, size)
    if error:
        await query.answer(error, show_alert=True)
        return

    context.user_data.pop('room_config', None)
    text = (
        f"✅ *Room Created!*\n\n"
        f"🏠 Room: *{room.room_code}*\n"
        f"💰 Fee: *{fee} coins*\n"
        f"👥 Players: *1/{size}*\n\n"
        f"⏳ Waiting for players to join...\n"
        f"Share this code: `{room.room_code}`"
    )
    await query.edit_message_text(text, reply_markup=room_waiting_keyboard(room), parse_mode='Markdown')


async def join_room_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    room_code = query.data.replace('join_', '')
    user = query.from_user

    room_data, error = await sync_to_async(_join_room_sync)(user.id, room_code)
    if error:
        await query.answer(error, show_alert=True)
        return

    await query.answer(f'Joined room {room_code}!')
    text = (
        f"🎮 *Room: {room_data['room_code']}*\n\n"
        f"💰 Fee: *{room_data['entry_fee']} coins*\n"
        f"👥 Players: *{room_data['player_count']}/{room_data['max_players']}*\n"
        f"🏆 Prize Pool: *{room_data['prize_pool']} coins*\n\n"
        f"⏳ Waiting for game to start..."
    )
    from games.models import GameRoom
    room = await sync_to_async(GameRoom.objects.get)(room_code=room_code)
    await query.edit_message_text(
        text,
        reply_markup=room_waiting_keyboard(room),
        parse_mode='Markdown'
    )


async def leave_room_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    room_code = query.data.replace('leave_', '')
    user = query.from_user

    try:
        fee = await sync_to_async(_leave_room_sync)(user.id, room_code)
    except Exception:
        await query.answer('Cannot leave this room!', show_alert=True)
        return

    await query.answer('Left the room, coins refunded!')
    text = f"🚪 You left room *{room_code}*. {fee} coins refunded."
    await query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')
