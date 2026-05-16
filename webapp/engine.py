import random
import threading
import time
import logging
from django.utils import timezone
from django.db import models as db_models, connection as db_connection, close_old_connections

logger = logging.getLogger('bingo.engine')


_active_games = set()
_lock = threading.Lock()


def run_game_engine(room_code):
    close_old_connections()

    from games.models import GameRoom, BingoCard, GameHistory
    from users.models import Player
    from wallets.models import Transaction

    try:
        room = GameRoom.objects.get(room_code=room_code)
    except GameRoom.DoesNotExist:
        logger.error(f'ENGINE FAIL: room={room_code} not_found')
        _active_games.discard(room_code)
        return

    cards = list(BingoCard.objects.filter(game_room=room).select_related('player'))
    if len(cards) < 2:
        logger.error(f'ENGINE FAIL: room={room_code} not_enough_players count={len(cards)}')
        room.status = 'finished'
        room.finished_at = timezone.now()
        room.save(update_fields=['status', 'finished_at'])
        _active_games.discard(room_code)
        return

    logger.info(f'ENGINE START: room={room_code} players={len(cards)} card_ids={[c.id for c in cards]}')

    numbers = list(range(1, 76))
    random.shuffle(numbers)
    called = []
    winner_card = None

    history, _ = GameHistory.objects.get_or_create(
        game_room=room,
        defaults={'numbers_called': [], 'prize_distributed': 0}
    )

    for number in numbers:
        if winner_card:
            break

        called.append(number)
        logger.info(f'ENGINE DRAW: room={room_code} number={number} called_so_far={len(called)}')

        for card in cards:
            card.mark_number(number)
            card.save(update_fields=['marked'])

            if card.check_win():
                winner_card = card
                logger.info(f'ENGINE WINNER: room={room_code} player={card.player.telegram_id} card={card.id}')
                break

        history.numbers_called = called
        history.save(update_fields=['numbers_called'])

        if not winner_card:
            time.sleep(3)

    room.refresh_from_db()
    room.status = 'finished'
    room.finished_at = timezone.now()

    if winner_card:
        winner = winner_card.player
        prize = room.prize_pool
        winner.coins = db_models.F('coins') + prize
        winner.wins = db_models.F('wins') + 1
        winner.xp = db_models.F('xp') + 100
        winner.games_played = db_models.F('games_played') + 1
        winner.save(update_fields=['coins', 'wins', 'xp', 'games_played'])
        room.winner = winner

        Transaction.objects.create(
            player=winner, amount=prize,
            transaction_type='game_win',
            description=f'Won room {room_code}'
        )
        logger.info(f'ENGINE PRIZE: room={room_code} winner={winner.telegram_id} prize={prize}')
    else:
        logger.info(f'ENGINE DRAW: room={room_code} no_winner')

    room.save()

    for card in cards:
        if card != winner_card:
            p = card.player
            p.losses = db_models.F('losses') + 1
            p.games_played = db_models.F('games_played') + 1
            p.xp = db_models.F('xp') + 25
            p.save(update_fields=['losses', 'games_played', 'xp'])

    history.refresh_from_db()
    history.prize_distributed = room.prize_pool if winner_card else 0
    if winner_card:
        history.winner = winner_card.player
    history.save(update_fields=['prize_distributed', 'winner'])

    logger.info(f'ENGINE END: room={room_code} finished')

    db_connection.close()


def start_game_thread(room_code):
    with _lock:
        if room_code in _active_games:
            logger.warning(f'ENGINE DUPLICATE PREVENTED: room={room_code}')
            return
        _active_games.add(room_code)

    logger.info(f'ENGINE THREAD START: room={room_code}')
    thread = threading.Thread(target=_run_and_cleanup, args=(room_code,), daemon=True)
    thread.start()


def _run_and_cleanup(room_code):
    try:
        run_game_engine(room_code)
    finally:
        _active_games.discard(room_code)
        db_connection.close()
        logger.info(f'ENGINE THREAD END: room={room_code}')
