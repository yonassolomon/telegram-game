import random
import threading
import time
import logging
from django.utils import timezone
from django.db import models as db_models, connection as db_connection, close_old_connections

logger = logging.getLogger('bingo.engine')

_active_games = set()
_lock = threading.Lock()
_room_events = {}
_room_paused = {}
_next_manual_number = {}


def _get_event(room_code):
    with _lock:
        if room_code not in _room_events:
            _room_events[room_code] = threading.Event()
        return _room_events[room_code]


def _clear_room(room_code):
    with _lock:
        _room_events.pop(room_code, None)
        _room_paused.pop(room_code, None)
        _next_manual_number.pop(room_code, None)


def trigger_next_number(room_code):
    with _lock:
        if room_code in _room_events:
            _room_events[room_code].set()
            return True
    return False


def call_specific_number(room_code, number):
    from games.models import GameRoom
    with _lock:
        if room_code not in _room_events or room_code not in _active_games:
            return False, 'Game engine not active for this room'

        try:
            room = GameRoom.objects.get(room_code=room_code)
        except GameRoom.DoesNotExist:
            return False, 'Room not found'

        if room.status != 'active':
            return False, 'Game is not active'

        if number < 1 or number > 75:
            return False, 'Number must be between 1 and 75'

        gs = room.game_state or {}
        called = gs.get('called', [])
        all_numbers = gs.get('numbers', [])

        if number in called:
            return False, f'Number {number} was already called'

        if number not in all_numbers:
            return False, f'Number {number} is not in this game pool'

        _next_manual_number[room_code] = number
        _room_events[room_code].set()
        return True, None


def pause_game(room_code):
    with _lock:
        _room_paused[room_code] = True
        if room_code in _room_events:
            _room_events[room_code].set()
    return True


def resume_game(room_code):
    with _lock:
        _room_paused.pop(room_code, None)
        if room_code in _room_events:
            _room_events[room_code].set()
    return True


def is_paused(room_code):
    with _lock:
        return _room_paused.get(room_code, False)


def switch_game_mode(room_code, mode):
    from games.models import GameRoom
    GameRoom.objects.filter(room_code=room_code).update(game_mode=mode)
    trigger_next_number(room_code)
    logger.info(f'ENGINE MODE SWITCH: room={room_code} mode={mode}')


def _pop_manual_number(room_code):
    with _lock:
        return _next_manual_number.pop(room_code, None)


def run_game_engine(room_code):
    close_old_connections()

    from games.models import GameRoom, BingoCard, GameHistory
    from users.models import Player
    from wallets.models import Transaction

    try:
        room = GameRoom.objects.get(room_code=room_code)
    except GameRoom.DoesNotExist:
        logger.error(f'ENGINE FAIL: room={room_code} not_found')
        _clear_room(room_code)
        return

    cards = list(BingoCard.objects.filter(game_room=room).select_related('player'))
    if len(cards) < 2:
        logger.error(f'ENGINE FAIL: room={room_code} not_enough_players count={len(cards)}')
        room.status = 'finished'
        room.finished_at = timezone.now()
        room.save(update_fields=['status', 'finished_at'])
        _clear_room(room_code)
        return

    numbers = list(range(1, 76))
    random.shuffle(numbers)

    room.game_state = {
        'numbers': numbers,
        'current_index': 0,
        'called': [],
        'paused': False,
    }
    room.game_mode = room.GameMode.AUTO
    room.save(update_fields=['game_state', 'game_mode'])

    logger.info(f'ENGINE START: room={room_code} players={len(cards)} mode=auto pool={numbers[:5]}...')

    history, _ = GameHistory.objects.get_or_create(
        game_room=room,
        defaults={'numbers_called': [], 'prize_distributed': 0}
    )

    winner_card = None
    event = _get_event(room_code)

    idx = 0
    while idx < len(numbers):
        if winner_card:
            break

        room.refresh_from_db(fields=['game_mode', 'game_state', 'status'])

        if room.game_mode == 'manual':
            logger.info(f'ENGINE WAITING MANUAL: room={room_code} idx={idx}')
            event.clear()
            event.wait(timeout=300)
            event.clear()

            room.refresh_from_db(fields=['game_mode', 'status'])
            if room.status != 'active':
                logger.info(f'ENGINE ABORTED: room={room_code} status={room.status}')
                break
            if room.game_mode == 'auto':
                logger.info(f'ENGINE SWITCHED TO AUTO: room={room_code}')
                continue

        manual_number = _pop_manual_number(room_code)

        while True:
            room.refresh_from_db(fields=['game_state'])
            if not is_paused(room_code):
                break
            event.clear()
            event.wait(timeout=1)
            event.clear()
            room.refresh_from_db(fields=['status'])
            if room.status != 'active':
                break
        if room.status != 'active':
            break

        room.refresh_from_db(fields=['game_state'])
        gs = room.game_state or {}
        called = list(gs.get('called', []))

        if manual_number is not None:
            number = manual_number
            if number in numbers:
                try:
                    pos = numbers.index(number)
                    if pos >= idx:
                        idx = pos
                except ValueError:
                    pass
            logger.info(f'ENGINE MANUAL CALL: room={room_code} admin_number={number}')
        else:
            number = numbers[idx]

        called.append(number)

        room.game_state = {
            'numbers': numbers,
            'current_index': idx + 1 if manual_number is None else max(idx + 1, numbers.index(number) + 1 if number in numbers else idx + 1),
            'called': called,
            'paused': is_paused(room_code),
        }
        room.save(update_fields=['game_state'])

        logger.info(f'ENGINE DRAW: room={room_code} number={number} called_count={len(called)} manual={manual_number is not None}')

        for card in cards:
            card.mark_number(number)
            card.save(update_fields=['marked'])
            if card.check_win():
                winner_card = card
                card.is_winner = True
                card.save(update_fields=['is_winner'])
                logger.info(f'ENGINE WINNER: room={room_code} player={card.player.telegram_id} card={card.id}')
                break

        history.numbers_called = called
        history.save(update_fields=['numbers_called'])

        if manual_number is None:
            idx += 1
        else:
            room.refresh_from_db(fields=['game_state'])
            idx = room.game_state.get('current_index', idx + 1)

        if not winner_card and room.game_mode == 'auto' and not is_paused(room_code) and manual_number is None:
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
    _clear_room(room_code)
    db_connection.close()


def start_game_thread(room_code, mode='auto'):
    with _lock:
        if room_code in _active_games:
            logger.warning(f'ENGINE DUPLICATE PREVENTED: room={room_code}')
            return
        _active_games.add(room_code)

    logger.info(f'ENGINE THREAD START: room={room_code} mode={mode}')
    thread = threading.Thread(target=_run_and_cleanup, args=(room_code,), daemon=True)
    thread.start()


def _run_and_cleanup(room_code):
    try:
        run_game_engine(room_code)
    finally:
        _active_games.discard(room_code)
        _clear_room(room_code)
        db_connection.close()
        logger.info(f'ENGINE THREAD END: room={room_code}')
