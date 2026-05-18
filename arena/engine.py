import random
import threading
import time
import logging
from django.utils import timezone
from django.db import models as db_models, connection as db_connection, close_old_connections

logger = logging.getLogger('bingo.arena')

_active_rounds = set()
_lock = threading.Lock()
_next_arena_number = {}
_arena_event = threading.Event()

WAITING_DURATION = 30
COOLDOWN_DURATION = 15


def call_specific_arena_number(number):
    from arena.models import GameRound
    with _lock:
        current = GameRound.objects.filter(status='active').order_by('-created_at').first()
        if not current:
            return False, 'No active Arena round'

        if number < 1 or number > 75:
            return False, 'Number must be 1–75'

        if number in current.numbers_called:
            return False, f'Number {number} already called'

        _next_arena_number[current.id] = number

        if current.call_mode != 'manual':
            GameRound.objects.filter(id=current.id).update(call_mode='manual')
            logger.info(f'ARENA MODE SWITCH: round={current.round_number} auto→manual')

    _arena_event.set()
    return True, None


def _pop_arena_number(round_id):
    with _lock:
        return _next_arena_number.pop(round_id, None)


def _clear_arena_round(round_id):
    with _lock:
        _next_arena_number.pop(round_id, None)


def _check_win(numbers_list, marked_set):
    size = 5
    free_idx = 12

    def cell(idx):
        return 1 if (idx == free_idx or numbers_list[idx] in marked_set) else 0

    grid = [[cell(i * size + j) for j in range(size)] for i in range(size)]

    for i in range(size):
        if sum(grid[i]) == size:
            return {'pattern': 'horizontal', 'cells': [[i, j] for j in range(size)],
                    'numbers': [0 if (i*size+j)==free_idx else numbers_list[i*size+j] for j in range(size)]}
        if sum(grid[j][i] for j in range(size)) == size:
            return {'pattern': 'vertical', 'cells': [[j, i] for j in range(size)],
                    'numbers': [0 if (j*size+i)==free_idx else numbers_list[j*size+i] for j in range(size)]}

    if sum(grid[i][i] for i in range(size)) == size:
        return {'pattern': 'diagonal', 'cells': [[i, i] for i in range(size)],
                'numbers': [0 if (i*size+i)==free_idx else numbers_list[i*size+i] for i in range(size)]}
    if sum(grid[i][size - 1 - i] for i in range(size)) == size:
        return {'pattern': 'diagonal_rev', 'cells': [[i, size-1-i] for i in range(size)],
                'numbers': [0 if (i*size+size-1-i)==free_idx else numbers_list[i*size+size-1-i] for i in range(size)]}

    return None


def run_round_engine(round_id):
    close_old_connections()

    from arena.models import GameRound, CardSelection
    from arena.cards import generate_card_by_number
    from users.models import Player
    from wallets.models import Transaction

    try:
        game_round = GameRound.objects.get(id=round_id)
    except GameRound.DoesNotExist:
        logger.error(f'ARENA FAIL: round={round_id} not_found')
        _active_rounds.discard(round_id)
        return

    game_round.status = 'waiting'
    game_round.waiting_started_at = timezone.now()
    game_round.save(update_fields=['status', 'waiting_started_at'])

    logger.info(f'ARENA WAITING: round={game_round.round_number} id={round_id}')

    for sec in range(WAITING_DURATION, 0, -1):
        time.sleep(1)

    game_round.refresh_from_db()
    game_round.status = 'active'
    game_round.started_at = timezone.now()
    game_round.save(update_fields=['status', 'started_at'])

    selections = list(CardSelection.objects.filter(round=game_round).select_related('player'))
    if len(selections) < 2:
        logger.info(f'ARENA CANCELLED: round={game_round.round_number} not_enough_players count={len(selections)}')
        from wallets.models import Transaction
        fee = game_round.entry_fee
        for sel in selections:
            sel.player.coins = db_models.F('coins') + fee
            sel.player.save(update_fields=['coins'])
            Transaction.objects.create(
                player=sel.player, amount=fee,
                transaction_type='draw_refund',
                description=f'Arena Round #{game_round.round_number} cancelled — not enough players'
            )
        logger.info(f'ARENA REFUND: round={game_round.round_number} refunded {len(selections)} players x {fee} coins')
        game_round.status = 'finished'
        game_round.finished_at = timezone.now()
        game_round.save(update_fields=['status', 'finished_at'])
        _start_next_round()
        _active_rounds.discard(round_id)
        return

    player_cards = {}
    for sel in selections:
        card_nums = generate_card_by_number(sel.card_number)
        player_cards[sel.player.telegram_id] = {
            'player': sel.player,
            'card_number': sel.card_number,
            'numbers': card_nums,
            'marked': set(),
            'card_obj': sel,
        }

    prize_pool = len(selections) * game_round.entry_fee
    from core.utils import calculate_prize
    winner_prize, platform_fee = calculate_prize(prize_pool)

    game_round.prize_pool = winner_prize
    game_round.save(update_fields=['prize_pool'])

    logger.info(f'ARENA ACTIVE: round={game_round.round_number} players={len(selections)} pot={prize_pool} fee={platform_fee} prize={winner_prize}')

    numbers = list(range(1, 76))
    random.shuffle(numbers)
    called = []
    winner_tg_id = None
    winner_card_num = None
    idx = 0

    while idx < len(numbers):
        if winner_tg_id:
            break

        room = GameRound.objects.get(id=round_id)
        if room.status != 'active':
            break

        current_mode = room.call_mode
        manual_number = None

        if current_mode == 'manual':
            manual_number = _pop_arena_number(game_round.id)
            if manual_number is None:
                logger.info(f'ARENA MANUAL WAIT: round={game_round.round_number}')
                _arena_event.clear()
                _arena_event.wait(timeout=300)
                room = GameRound.objects.get(id=round_id)
                if room.status != 'active':
                    break
                if room.call_mode == 'auto':
                    logger.info(f'ARENA MODE SWITCHED TO AUTO: round={game_round.round_number}')
                    continue
                manual_number = _pop_arena_number(game_round.id)
                if manual_number is None:
                    continue
        else:
            manual_number = _pop_arena_number(game_round.id)

        if manual_number is not None:
            number = manual_number
            if number in numbers:
                try:
                    pos = numbers.index(number)
                    if pos >= idx:
                        idx = pos
                except ValueError:
                    pass
            logger.info(f'ARENA MANUAL CALL: round={game_round.round_number} number={number}')
        else:
            number = numbers[idx]

        called.append(number)
        idx += 1

        for tg_id, data in player_cards.items():
            if number in data['numbers']:
                data['marked'].add(number)

            win_info = _check_win(data['numbers'], data['marked'])
            if win_info:
                winner_tg_id = tg_id
                winner_card_num = data['card_number']
                logger.info(f'ARENA WINNER: round={game_round.round_number} player={tg_id} card={winner_card_num} pattern={win_info["pattern"]}')

        game_round.numbers_called = called
        game_round.save(update_fields=['numbers_called'])

        if not winner_tg_id and manual_number is None:
            _arena_event.clear()
            _arena_event.wait(timeout=3)

    game_round.refresh_from_db()
    game_round.status = 'finished'
    game_round.finished_at = timezone.now()

    if winner_tg_id:
        winner_data = player_cards[winner_tg_id]
        winner = winner_data['player']
        winner.coins = db_models.F('coins') + winner_prize
        winner.wins = db_models.F('wins') + 1
        winner.games_played = db_models.F('games_played') + 1
        winner.xp = db_models.F('xp') + 200
        winner.save(update_fields=['coins', 'wins', 'games_played', 'xp'])

        game_round.winner = winner
        game_round.winner_card_number = winner_card_num

        Transaction.objects.create(
            player=winner, amount=winner_prize,
            transaction_type='game_win',
            description=f'Arena Round #{game_round.round_number} win'
        )
        Transaction.objects.create(
            player=winner, amount=-platform_fee,
            transaction_type='house_fee',
            description=f'Arena Round #{game_round.round_number} house fee'
        )
        logger.info(f'ARENA PRIZE: round={game_round.round_number} winner={winner_tg_id} prize={winner_prize} fee={platform_fee}')
    else:
        for tg_id, data in player_cards.items():
            p = data['player']
            p.coins = db_models.F('coins') + game_round.entry_fee
            p.games_played = db_models.F('games_played') + 1
            p.save(update_fields=['coins', 'games_played'])
            Transaction.objects.create(
                player=p, amount=game_round.entry_fee,
                transaction_type='draw_refund',
                description=f'Arena Round #{game_round.round_number} draw refund'
            )
        logger.info(f'ARENA DRAW: round={game_round.round_number} refunding all')

    for tg_id, data in player_cards.items():
        if tg_id != winner_tg_id:
            p = data['player']
            p.losses = db_models.F('losses') + 1
            p.games_played = db_models.F('games_played') + 1
            p.xp = db_models.F('xp') + 25
            p.save(update_fields=['losses', 'games_played', 'xp'])

    game_round.save()

    logger.info(f'ARENA END: round={game_round.round_number} finished')

    _active_rounds.discard(round_id)
    db_connection.close()

    time.sleep(COOLDOWN_DURATION)
    _start_next_round()


def _start_next_round():
    from arena.models import GameRound
    last_round = GameRound.objects.order_by('-round_number').first()
    next_num = (last_round.round_number + 1) if last_round else 1

    new_round = GameRound.objects.create(round_number=next_num, status='waiting')
    logger.info(f'ARENA NEXT ROUND: round={next_num} id={new_round.id}')

    start_round_thread(new_round.id)


def start_round_thread(round_id):
    with _lock:
        if round_id in _active_rounds:
            return
        _active_rounds.add(round_id)

    thread = threading.Thread(target=_run_safe, args=(round_id,), daemon=True)
    thread.start()
    logger.info(f'ARENA THREAD START: round={round_id}')


def _run_safe(round_id):
    try:
        run_round_engine(round_id)
    except Exception as e:
        logger.error(f'ARENA ENGINE CRASH: round={round_id} error={e}')
    finally:
        _active_rounds.discard(round_id)
        db_connection.close()


def ensure_round_running():
    from arena.models import GameRound
    with _lock:
        if _active_rounds:
            return

    current = GameRound.objects.filter(status__in=('waiting', 'active')).order_by('-created_at').first()
    if not current:
        current = GameRound.objects.create(round_number=1)
    start_round_thread(current.id)
