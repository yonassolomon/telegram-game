import asyncio
from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import ContextTypes
from django.utils import timezone
from django.db import models
from core.utils import format_card, generate_random_numbers
from bot.keyboards.inline import game_over_keyboard


def _start_game_sync(room_code):
    from games.models import GameRoom, BingoCard
    room = GameRoom.objects.select_for_update().get(room_code=room_code)
    if room.status != 'waiting':
        return None, 'Game already started or finished!'
    cards = list(BingoCard.objects.filter(game_room=room).select_related('player'))
    if len(cards) < 2:
        return None, 'Need at least 2 players to start!'
    room.status = 'active'
    room.started_at = timezone.now()
    room.save(update_fields=['status', 'started_at'])
    card_data = []
    for c in cards:
        card_data.append({
            'id': c.id,
            'tg_id': c.player.telegram_id,
        })
    return {'room_code': room_code, 'cards': card_data}, None


def _format_card_sync(card_id):
    from games.models import BingoCard
    card = BingoCard.objects.select_related('game_room').get(id=card_id)
    card_display = format_card(card.numbers, card.marked)
    text = (
        f"🎲 *Your Bingo Card* | Room: `{card.game_room.room_code}`\n\n"
        f"{card_display}\n\n"
        f"📌 Marked: {len(card.marked)}/24 | 🎯 Playing..."
    )
    return text


def _mark_and_check_sync(card_id, number):
    from games.models import BingoCard
    card = BingoCard.objects.get(id=card_id)
    card.mark_number(number)
    card.save(update_fields=['marked'])
    return card.check_win(), card.player.telegram_id


def _finalize_game_sync(room_code, winner_tg_id):
    from games.models import GameRoom, BingoCard, GameHistory
    from users.models import Player
    from wallets.models import Transaction

    room = GameRoom.objects.get(room_code=room_code)
    cards = list(BingoCard.objects.filter(game_room=room).select_related('player'))

    room.status = 'finished'
    room.finished_at = timezone.now()

    winner_name = None
    prize = 0
    if winner_tg_id:
        winner = Player.objects.get(telegram_id=winner_tg_id)
        prize = room.prize_pool
        winner.coins = models.F('coins') + prize
        winner.wins = models.F('wins') + 1
        winner.xp = models.F('xp') + 100
        winner.games_played = models.F('games_played') + 1
        winner.save(update_fields=['coins', 'wins', 'xp', 'games_played'])
        room.winner = winner
        Transaction.objects.create(
            player=winner, amount=prize,
            transaction_type='game_win', description=f'Won room {room_code}'
        )
        winner_name = winner.first_name or winner.username

    room.save()

    player_tg_ids = []
    for card in cards:
        p = card.player
        player_tg_ids.append(p.telegram_id)
        if p.telegram_id != winner_tg_id:
            p.losses = models.F('losses') + 1
            p.games_played = models.F('games_played') + 1
            p.xp = models.F('xp') + 25
            p.save(update_fields=['losses', 'games_played', 'xp'])

    GameHistory.objects.create(
        game_room=room, winner=room.winner,
        numbers_called=[], prize_distributed=prize,
    )

    return {
        'winner_name': winner_name,
        'prize': prize,
        'has_winner': winner_tg_id is not None,
        'player_tg_ids': player_tg_ids,
    }


async def start_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    room_code = query.data.replace('start_', '')

    result, error = await sync_to_async(_start_game_sync)(room_code)
    if error:
        await query.answer(error, show_alert=True)
        return

    await query.message.delete()

    cards = result['cards']
    card_messages = {}

    for card_info in cards:
        cid = card_info['id']
        tg_id = card_info['tg_id']
        text = await sync_to_async(_format_card_sync)(cid)
        try:
            msg = await context.bot.send_message(
                chat_id=tg_id,
                text=text,
                parse_mode='Markdown'
            )
            card_messages[cid] = {'chat_id': tg_id, 'message_id': msg.message_id}
        except Exception:
            pass

    context.bot_data[f'game_{room_code}'] = {
        'cards': cards,
        'card_messages': card_messages,
    }

    asyncio.create_task(_run_game(context, room_code, cards, card_messages))


async def _run_game(context, room_code, cards, card_messages):
    numbers = generate_random_numbers()
    called = []
    game_over = False
    winner_tg_id = None

    for number in numbers:
        if game_over:
            break
        called.append(number)

        for card_info in cards:
            cid = card_info['id']
            is_win, player_tg = await sync_to_async(_mark_and_check_sync)(cid, number)
            if is_win:
                winner_tg_id = player_tg
                game_over = True
                break

        for card_info in cards:
            cid = card_info['id']
            text = await sync_to_async(_format_card_sync)(cid)
            msg_info = card_messages.get(cid)
            if msg_info:
                try:
                    await context.bot.edit_message_text(
                        chat_id=msg_info['chat_id'],
                        message_id=msg_info['message_id'],
                        text=text,
                        parse_mode='Markdown'
                    )
                except Exception:
                    pass

        await asyncio.sleep(2)

    result = await sync_to_async(_finalize_game_sync)(room_code, winner_tg_id)

    if result['has_winner']:
        win_text = (
            f"🎉 *BINGO! We Have a Winner!* 🎉\n\n"
            f"🏆 *{result['winner_name']}* won the game!\n\n"
            f"💰 Prize: *{result['prize']} coins*\n"
            f"🎯 Numbers called: *{len(called)}*\n\n"
            f"Congratulations! 🥳🎊🎈"
        )
    else:
        win_text = "🤝 *Game Over — It's a Draw!*\n\nNo winner this round.\nAll players get XP!\n\nTry again!"

    for tg_id in result['player_tg_ids']:
        try:
            await context.bot.send_message(
                chat_id=tg_id,
                text=win_text,
                reply_markup=game_over_keyboard(tg_id),
                parse_mode='Markdown'
            )
        except Exception:
            pass
