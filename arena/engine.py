import random
import logging
from django.utils import timezone
from django.db import transaction as db_transaction, models as db_models, close_old_connections
from core.utils import calculate_prize

logger = logging.getLogger('bingo.arena')

WAITING_DURATION = 30


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


def call_specific_arena_number(number):
    from arena.models import GameRound
    try:
        current = GameRound.objects.filter(status='active').order_by('-created_at').first()
        if not current:
            return False, 'No active Arena round'
        if number < 1 or number > 75:
            return False, 'Number must be 1–75'
        if number in current.numbers_called:
            return False, f'Number {number} already called'
        called = list(current.numbers_called or [])
        called.append(number)
        GameRound.objects.filter(id=current.id, status='active').update(numbers_called=called)
        return True, None
    except Exception as e:
        logger.error(f'ARENA CALL ERROR: {e}')
        return False, 'Internal error'


def tick():
    from arena.models import GameRound, CardSelection
    from arena.cards import generate_card_by_number
    from users.models import Player
    from wallets.models import Transaction

    close_old_connections()

    round = GameRound.objects.filter(status='waiting').order_by('-created_at').first()
    if not round:
        round = GameRound.objects.filter(status='active').order_by('-created_at').first()

    if not round or round.status == 'finished':
        return

    if round.status == 'waiting':
        if not round.waiting_started_at:
            round.waiting_started_at = timezone.now()
            round.save(update_fields=['waiting_started_at'])
            return

        elapsed = (timezone.now() - round.waiting_started_at).total_seconds()
        if elapsed < WAITING_DURATION:
            return

        with db_transaction.atomic():
            r = GameRound.objects.select_for_update().get(id=round.id)
            if r.status != 'waiting':
                return
            selections = list(CardSelection.objects.filter(round=r).select_related('player'))
            if len(selections) < 2:
                fee = r.entry_fee
                for sel in selections:
                    Player.objects.filter(id=sel.player_id).update(coins=db_models.F('coins') + fee)
                    Transaction.objects.create(
                        player=sel.player, amount=fee, transaction_type='draw_refund',
                        description=f'Arena Round #{r.round_number} cancelled')
                r.status = 'finished'
                r.finished_at = timezone.now()
                r.save(update_fields=['status', 'finished_at'])
                logger.info(f'ARENA CANCELLED: round={r.round_number} players={len(selections)}')
                _start_next_round()
                return

            numbers = list(range(1, 76))
            random.shuffle(numbers)
            total_pot = len(selections) * r.entry_fee
            winner_prize, _ = calculate_prize(total_pot)
            r.status = 'active'
            r.started_at = timezone.now()
            r.prize_pool = winner_prize
            r.game_state = {'numbers': numbers, 'idx': 0}
            r.numbers_called = []
            r.save(update_fields=['status', 'started_at', 'prize_pool', 'game_state', 'numbers_called'])
            logger.info(f'ARENA STARTED: round={r.round_number} players={len(selections)} prize={winner_prize}')

    elif round.status == 'active':
        gs = round.game_state or {}
        numbers = gs.get('numbers', [])
        idx = gs.get('idx', 0)
        called = list(round.numbers_called or [])
        last_time = gs.get('last_call_time', 0)
        now = timezone.now().timestamp()

        if idx > 0 and now - last_time < 3:
            return

        if idx >= len(numbers):
            round.status = 'finished'
            round.finished_at = timezone.now()
            round.save(update_fields=['status', 'finished_at'])
            selections = CardSelection.objects.filter(round=round)
            fee = round.entry_fee
            for sel in selections:
                Player.objects.filter(id=sel.player_id).update(coins=db_models.F('coins') + fee)
                Transaction.objects.create(player=sel.player, amount=fee, transaction_type='draw_refund',
                                           description=f'Arena Round #{round.round_number} draw')
            logger.info(f'ARENA DRAW: round={round.round_number}')
            _start_next_round()
            return

        number = numbers[idx]
        called.append(number)
        gs['idx'] = idx + 1
        gs['last_call_time'] = now
        round.game_state = gs
        round.numbers_called = called
        round.save(update_fields=['game_state', 'numbers_called'])

        selections = CardSelection.objects.filter(round=round).select_related('player')
        for sel in selections:
            numbers_list = generate_card_by_number(sel.card_number)
            marked = {n for n in called if n in numbers_list}
            win_info = _check_win(numbers_list, marked)
            if win_info:
                with db_transaction.atomic():
                    r = GameRound.objects.select_for_update().get(id=round.id)
                    if r.status != 'active':
                        return
                    total_pot = len(selections) * r.entry_fee
                    winner_prize, house_fee = calculate_prize(total_pot)
                    r.prize_pool = winner_prize
                    r.winner = sel.player
                    sel.player.coins = db_models.F('coins') + winner_prize
                    sel.player.wins = db_models.F('wins') + 1
                    sel.player.games_played = db_models.F('games_played') + 1
                    sel.player.xp = db_models.F('xp') + 200
                    sel.player.save(update_fields=['coins', 'wins', 'games_played', 'xp'])
                    Transaction.objects.create(
                        player=sel.player, amount=winner_prize,
                        transaction_type='game_win',
                        description=f'Arena Round #{r.round_number} win')
                    if round.game_state:
                        round.game_state['winner_pattern'] = win_info
                    r.status = 'finished'
                    r.finished_at = timezone.now()
                    r.save()
                    logger.info(f'ARENA WINNER: round={r.round_number} player={sel.player.telegram_id} prize={winner_prize}')
                    _start_next_round()
                return


def _start_next_round():
    from arena.models import GameRound
    last = GameRound.objects.order_by('-round_number').first()
    next_num = (last.round_number + 1) if last else 1
    GameRound.objects.create(round_number=next_num, status='waiting', waiting_started_at=timezone.now())
    logger.info(f'ARENA NEXT: round={next_num}')


def ensure_round_running():
    from arena.models import GameRound
    if GameRound.objects.filter(status__in=('waiting', 'active')).exists():
        return
    last = GameRound.objects.order_by('-round_number').first()
    next_num = (last.round_number + 1) if last else 1
    GameRound.objects.create(round_number=next_num, status='waiting', waiting_started_at=timezone.now())
    logger.info(f'ARENA ENSURE: round={next_num}')
