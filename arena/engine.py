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
    current = GameRound.objects.filter(status='active').order_by('-created_at').first()
    if not current:
        return False, 'No active Arena round'
    if number < 1 or number > 75:
        return False, 'Number must be 1-75'
    if number in current.numbers_called:
        return False, f'Number {number} already called'
    called = list(current.numbers_called or [])
    called.append(number)
    GameRound.objects.filter(id=current.id, status='active').update(numbers_called=called)
    return True, None


def tick():
    from arena.models import GameRound, CardSelection
    from arena.cards import generate_card_by_number
    from users.models import Player
    from wallets.models import Transaction

    close_old_connections()

    _randomize_bot_coins()

    round_obj = GameRound.objects.filter(status='waiting').order_by('-created_at').first()
    if not round_obj:
        round_obj = GameRound.objects.filter(status='active').order_by('-created_at').first()

    if not round_obj:
        return

    if round_obj.status == 'waiting':
        close_old_connections()
        if not round_obj.waiting_started_at:
            round_obj.waiting_started_at = timezone.now()
            round_obj.save(update_fields=['waiting_started_at'])
            return
        elapsed = (timezone.now() - round_obj.waiting_started_at).total_seconds()
        if elapsed < WAITING_DURATION:
            return
        with db_transaction.atomic():
            r = GameRound.objects.select_for_update().get(id=round_obj.id)
            if r.status != 'waiting':
                return
            selections = list(CardSelection.objects.filter(round=r).select_related('player'))
            if len(selections) < 2:
                fee = r.entry_fee
                done = set()
                for sel in selections:
                    if sel.player_id not in done:
                        done.add(sel.player_id)
                        total_fee = fee * len([s for s in selections if s.player_id == sel.player_id])
                        Player.objects.filter(id=sel.player_id).update(coins=db_models.F('coins') + total_fee)
                    Transaction.objects.create(player=sel.player, amount=fee, transaction_type='draw_refund',
                                               description=f'Arena Round #{r.round_number} cancelled (card #{sel.card_number})')
                r.status = 'finished'
                r.finished_at = timezone.now()
                r.save(update_fields=['status', 'finished_at'])
                logger.info(f'ARENA CANCELLED: round={r.round_number}')
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

            total_pot = len(selections) * r.entry_fee
            winner_prize, _ = calculate_prize(total_pot)
            r.prize_pool = winner_prize
            r.save(update_fields=['prize_pool'])

            logger.info(f'ARENA STARTED: round={r.round_number} players={len(selections)} prize={winner_prize}')
        return

    if round_obj.status == 'active':
        close_old_connections()
        if round_obj.call_mode == 'manual':
            _check_manual_winner(round_obj)
            return

        gs = round_obj.game_state or {}
        numbers = gs.get('numbers', [])
        idx = gs.get('idx', 0)
        now = timezone.now().timestamp()
        last_call = gs.get('last_call', 0)

        if idx > 0 and now - last_call < 3:
            return

        if idx >= len(numbers):
            _finish_draw(round_obj)
            return

        number = numbers[idx]
        called = list(round_obj.numbers_called or [])
        called.append(number)
        gs['idx'] = idx + 1
        gs['last_call'] = now
        round_obj.numbers_called = called
        round_obj.game_state = gs
        round_obj.save(update_fields=['numbers_called', 'game_state'])

        selections = CardSelection.objects.filter(round=round_obj).select_related('player')
        for sel in selections:
            numbers_list = generate_card_by_number(sel.card_number)
            marked = {n for n in called if n in numbers_list}
            if _check_win(numbers_list, marked):
                _award_winner(round_obj, sel, len(selections))
                return


def _check_manual_winner(round_obj):
    from arena.models import CardSelection
    from arena.cards import generate_card_by_number
    selections = CardSelection.objects.filter(round=round_obj).select_related('player')
    called = list(round_obj.numbers_called or [])
    for sel in selections:
        numbers_list = generate_card_by_number(sel.card_number)
        marked = {n for n in called if n in numbers_list}
        if _check_win(numbers_list, marked):
            _award_winner(round_obj, sel, len(selections))
            return


def _award_winner(round_obj, sel, player_count):
    from arena.models import GameRound
    from wallets.models import Transaction
    with db_transaction.atomic():
        r = GameRound.objects.select_for_update().get(id=round_obj.id)
        if r.status != 'active':
            return
        total_pot = player_count * r.entry_fee
        winner_prize, house_fee = calculate_prize(total_pot)
        r.prize_pool = winner_prize
        r.winner = sel.player
        sel.player.coins = db_models.F('coins') + winner_prize
        sel.player.wins = db_models.F('wins') + 1
        sel.player.games_played = db_models.F('games_played') + 1
        sel.player.xp = db_models.F('xp') + 200
        sel.player.save(update_fields=['coins', 'wins', 'games_played', 'xp'])
        Transaction.objects.create(player=sel.player, amount=winner_prize, transaction_type='game_win',
                                   description=f'Arena Round #{r.round_number} win')
        Transaction.objects.create(player=sel.player, amount=-house_fee, transaction_type='house_fee',
                                   description=f'Arena Round #{r.round_number} house fee')
        from arena.models import CardSelection
        all_players = CardSelection.objects.filter(round=r)
        done = set()
        for s in all_players:
            if s.player_id != sel.player_id and s.player_id not in done:
                done.add(s.player_id)
                s.player.games_played = db_models.F('games_played') + 1
                s.player.losses = db_models.F('losses') + 1
                s.player.save(update_fields=['games_played', 'losses'])
        r.status = 'finished'
        r.finished_at = timezone.now()
        r.save()
        logger.info(f'ARENA WINNER: round={r.round_number} player={sel.player.telegram_id} prize={winner_prize}')
    _start_next_round()
    _update_streaks(round_obj)


def _finish_draw(round_obj):
    from wallets.models import Transaction
    from users.models import Player
    fee = round_obj.entry_fee
    unique_players = set()
    for sel in round_obj.selections.all():
        total_fee = fee * round_obj.selections.filter(player_id=sel.player_id).count()
        if sel.player_id not in unique_players:
            unique_players.add(sel.player_id)
            Player.objects.filter(id=sel.player_id).update(
                coins=db_models.F('coins') + total_fee,
                games_played=db_models.F('games_played') + 1
            )
        Transaction.objects.create(player=sel.player, amount=fee, transaction_type='draw_refund',
                                   description=f'Arena Round #{round_obj.round_number} draw (card #{sel.card_number})')
    round_obj.status = 'finished'
    round_obj.finished_at = timezone.now()
    round_obj.save(update_fields=['status', 'finished_at'])
    logger.info(f'ARENA DRAW: round={round_obj.round_number}')
    _start_next_round()
    _update_streaks(round_obj)


def _add_bot_players(round_obj, human_count):
    from arena.models import CardSelection
    from users.models import Player
    import random as _random

    bot_count = _random.randint(15, 35)
    bot_players = list(Player.objects.filter(telegram_id__gte=900000000, telegram_id__lte=900000007))
    if not bot_players:
        return

    chosen = _random.sample(bot_players, min(bot_count, len(bot_players)))

    existing_cards = set(CardSelection.objects.filter(round=round_obj).values_list('card_number', flat=True))
    available = [i for i in range(1, 101) if i not in existing_cards]

    for bot in chosen:
        if not available:
            break
        card_num = _random.choice(available)
        available.remove(card_num)
        CardSelection.objects.create(round=round_obj, player=bot, card_number=card_num)

    new_pot = CardSelection.objects.filter(round=round_obj).count() * round_obj.entry_fee
    new_prize, _ = calculate_prize(new_pot)
    from arena.models import GameRound
    GameRound.objects.filter(id=round_obj.id).update(prize_pool=new_prize)

    logger.info(f'BOTS JOINED: round={round_obj.round_number} bots={len(chosen)} total={CardSelection.objects.filter(round=round_obj).count()}')


def _update_streaks(round_obj):
    from datetime import timedelta
    from arena.models import CardSelection
    today = timezone.now().date()
    selections = CardSelection.objects.filter(round=round_obj).select_related('player')
    done = set()
    for sel in selections:
        p = sel.player
        if p.id in done:
            continue
        done.add(p.id)
        if p.last_streak_date == today:
            continue
        if p.last_streak_date == today - timedelta(days=1):
            p.streak_count = db_models.F('streak_count') + 1
        else:
            p.streak_count = 1
        p.last_streak_date = today
        p.save(update_fields=['streak_count', 'last_streak_date'])


def _start_next_round():
    from arena.models import GameRound
    last = GameRound.objects.order_by('-round_number').first()
    next_num = (last.round_number + 1) if last else 1
    GameRound.objects.create(round_number=next_num, status='waiting', waiting_started_at=timezone.now())
    logger.info(f'ARENA NEXT: round={next_num}')


def _randomize_bot_coins():
    from users.models import Player
    import random as _random
    now = timezone.now()
    last = getattr(_randomize_bot_coins, '_last_run', None)
    if last and (now - last).total_seconds() < 120:
        return
    _randomize_bot_coins._last_run = now
    bot_names = ['Alemayehu', 'NatiFaya', 'Robel', 'Moges', 'Kasahun', 'Mimi', 'Tages', 'Abushi',
        'Bilisummaa', 'Carraa', 'Ifaa', 'Cimsa', 'Jaalalaa', 'Gammachuu', 'Wolene', 'Mesqan',
        'Eyob Tadese', 'Dawit Bekele', 'Yonatan Alemu', 'Henok Getachew', 'Biruk Tadesse',
        'Natnael Fikru', 'Yared Assefa', 'Abel Tesfaye', 'Bereket Demissie', 'Nahom Girma',
        'Samuel Mekonnen', 'Biniyam Desta', 'Robel Kassahun', 'Surafel Abebe', 'Melaku Belay',
        'Tamirat Haile', 'Tewodros Kebede', 'Misganaw Solomon', 'Anibe']
    for i, name in enumerate(bot_names):
        p, created = Player.objects.get_or_create(
            telegram_id=900000000 + i,
            defaults={'first_name': name, 'coins': _random.randint(20, 350), 'wins': _random.randint(5, 10)}
        )
        new_coins = _random.randint(20, 350)
        update_fields = {'coins': new_coins}
        if created or p.wins < 5:
            update_fields['wins'] = _random.randint(5, 10)
        Player.objects.filter(telegram_id=900000000 + i).update(**update_fields)


def ensure_bots_in_round(round_obj):
    from arena.models import CardSelection
    from users.models import Player
    import random as _random

    bot_names = ['Alemayehu', 'NatiFaya', 'Robel', 'Moges', 'Kasahun', 'Mimi', 'Tages', 'Abushi',
        'Bilisummaa', 'Carraa', 'Ifaa', 'Cimsa', 'Jaalalaa', 'Gammachuu', 'Wolene', 'Mesqan',
        'Eyob Tadese', 'Dawit Bekele', 'Yonatan Alemu', 'Henok Getachew', 'Biruk Tadesse',
        'Natnael Fikru', 'Yared Assefa', 'Abel Tesfaye', 'Bereket Demissie', 'Nahom Girma',
        'Samuel Mekonnen', 'Biniyam Desta', 'Robel Kassahun', 'Surafel Abebe', 'Melaku Belay',
        'Tamirat Haile', 'Tewodros Kebede', 'Misganaw Solomon', 'Anibe']
    bot_players = []
    for i, name in enumerate(bot_names):
        tg_id = 900000000 + i
        p, created = Player.objects.get_or_create(
            telegram_id=900000000 + i,
            defaults={'first_name': name, 'coins': _random.randint(20, 350), 'wins': _random.randint(5, 10)}
        )
        if created or p.wins < 5:
            Player.objects.filter(telegram_id=900000000 + i).update(wins=_random.randint(5, 10))
        bot_players.append(p)

    existing_bots = CardSelection.objects.filter(
        round=round_obj, player__in=bot_players
    ).count()
    if existing_bots > 0:
        return

    bot_count = _random.randint(2, 5)
    chosen = _random.sample(bot_players, min(bot_count, len(bot_players)))
    existing_cards = set(CardSelection.objects.filter(round=round_obj).values_list('card_number', flat=True))
    available = [i for i in range(1, 101) if i not in existing_cards]

    for bot in chosen:
        if not available:
            break
        card_num = _random.choice(available)
        available.remove(card_num)
        CardSelection.objects.create(round=round_obj, player=bot, card_number=card_num)

    new_count = CardSelection.objects.filter(round=round_obj).count()
    new_pot = new_count * round_obj.entry_fee
    new_prize, _ = calculate_prize(new_pot)
    from arena.models import GameRound
    GameRound.objects.filter(id=round_obj.id).update(prize_pool=new_prize)

    logger.info(f'BOTS JOINED WAITING: round={round_obj.round_number} bots={len(chosen)} total={new_count} prize={new_prize}')


def ensure_round_running():
    from arena.models import GameRound, CardSelection
    if GameRound.objects.filter(status__in=('waiting', 'active')).exists():
        waiting = GameRound.objects.filter(status='waiting').order_by('-created_at').first()
        if waiting:
            ensure_bots_in_round(waiting)
        return
    last = GameRound.objects.order_by('-round_number').first()
    next_num = (last.round_number + 1) if last else 1
    new_round = GameRound.objects.create(round_number=next_num, status='waiting', waiting_started_at=timezone.now())
    ensure_bots_in_round(new_round)
    logger.info(f'ARENA ENSURE: round={next_num}')
