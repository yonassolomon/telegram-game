import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone
from arena.models import GameRound, CardSelection
from arena.cards import generate_card_by_number, format_card_grid
from arena.engine import ensure_round_running
from webapp.views import get_player_from_request
from wallets.models import Transaction
from users.models import Player

logger = logging.getLogger('bingo.arena')


def _get_card_grid(card_number, marked_set):
    from arena.cards import generate_card_by_number, format_card_grid
    numbers = generate_card_by_number(card_number)
    return format_card_grid(numbers, marked_set)


def lobby(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    ensure_round_running()

    current = GameRound.objects.filter(status__in=('waiting', 'active', 'cooldown')).order_by('-created_at').first()
    if not current:
        current = GameRound.objects.order_by('-created_at').first()

    if current and current.status == 'waiting':
        from arena.engine import ensure_bots_in_round
        ensure_bots_in_round(current)

    selections = list(CardSelection.objects.filter(round=current).select_related('player'))
    taken_cards = {s.card_number: s.player.first_name for s in selections}

    my_cards = []
    if current:
        my_cards = list(CardSelection.objects.filter(round=current, player=player).values_list('card_number', flat=True))

    can_claim = player.can_claim_daily()
    next_daily = ''
    next_daily_seconds = 0
    if not can_claim and player.last_daily_bonus:
        secs = 86400 - (timezone.now() - player.last_daily_bonus).total_seconds()
        next_daily_seconds = max(0, int(secs))
        h = next_daily_seconds // 3600
        m = (next_daily_seconds % 3600) // 60
        s = next_daily_seconds % 60
        next_daily = f'{h:02d}:{m:02d}:{s:02d}'
        if secs <= 0:
            can_claim = True

    return render(request, 'arena/lobby.html', {
        'player': player,
        'round': current,
        'my_cards': my_cards,
        'my_cards_json': json.dumps(my_cards),
        'can_claim_daily': can_claim,
        'next_daily': next_daily,
        'next_daily_seconds': next_daily_seconds,
        'taken_cards_json': json.dumps(taken_cards),
        'my_card_grids_json': json.dumps([_get_card_grid(c, set()) for c in my_cards]) if my_cards else '[]',
    })


@csrf_exempt
@require_POST
def api_select_card(request, round_id):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        card_num = int(request.POST.get('card_number', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid card number'}, status=400)

    if card_num < 1 or card_num > 200:
        return JsonResponse({'error': 'Card must be 1-200'}, status=400)

    game_round = get_object_or_404(GameRound, id=round_id)

    if game_round.status != 'waiting':
        return JsonResponse({'error': 'Card selection is closed. Game already started.'}, status=400)

    with db_transaction.atomic():
        my_existing = list(CardSelection.objects.select_for_update().filter(round=game_round, player=player))

        existing_for_card = next((s for s in my_existing if s.card_number == card_num), None)
        if existing_for_card:
            existing_for_card.delete()
            Player.objects.filter(id=player.id).update(coins=F('coins') + game_round.entry_fee)
            Transaction.objects.create(
                player=player, amount=game_round.entry_fee,
                transaction_type='draw_refund',
                description=f'Deselected card #{card_num} in Arena Round #{game_round.round_number}'
            )
            _recalc_prize(game_round)
            my_remaining = list(CardSelection.objects.filter(round=game_round, player=player).values_list('card_number', flat=True))
            logger.info(f'CARD DESELECTED: round={game_round.round_number} player={player.telegram_id} card={card_num}')
            return JsonResponse({'success': True, 'card_number': card_num, 'action': 'deselect', 'my_cards': my_remaining})

        if len(my_existing) >= CardSelection.MAX_CARDS_PER_PLAYER:
            return JsonResponse({'error': f'Maximum {CardSelection.MAX_CARDS_PER_PLAYER} cards allowed.'}, status=400)

        p = Player.objects.select_for_update().get(id=player.id)
        if p.coins < game_round.entry_fee:
            return JsonResponse({'error': f'Insufficient coins. Need {game_round.entry_fee}, have {p.coins}.'}, status=400)

        existing_card = CardSelection.objects.filter(round=game_round, card_number=card_num).first()
        if existing_card:
            return JsonResponse({'error': f'Card {card_num} already chosen by another player'}, status=409)

        CardSelection.objects.create(round=game_round, player=p, card_number=card_num)

        from agents.commission import process_entry_and_commission
        process_entry_and_commission(p, game_round.entry_fee, 'arena', f'Round #{game_round.round_number}')

        Transaction.objects.create(
            player=p, amount=-game_round.entry_fee,
            transaction_type='game_entry',
            description=f'Arena Round #{game_round.round_number} entry (card #{card_num})'
        )

    _recalc_prize(game_round)
    my_remaining = list(CardSelection.objects.filter(round=game_round, player=player).values_list('card_number', flat=True))

    logger.info(f'CARD SELECTED: round={game_round.round_number} player={player.telegram_id} card={card_num} total={len(my_remaining)}')
    return JsonResponse({'success': True, 'card_number': card_num, 'action': 'select', 'my_cards': my_remaining})

def _recalc_prize(game_round):
    from core.utils import calculate_prize
    total_pot = game_round.entry_fee * CardSelection.objects.filter(round=game_round).count()
    winner_prize, _ = calculate_prize(total_pot)
    GameRound.objects.filter(id=game_round.id).update(prize_pool=winner_prize)


@csrf_exempt
@require_POST
def api_leave_arena(request, round_id):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    game_round = get_object_or_404(GameRound, id=round_id)
    if game_round.status != 'waiting':
        return JsonResponse({'error': 'Game already started. Cannot leave.'}, status=400)

    my_sels = list(CardSelection.objects.filter(round=game_round, player=player))
    if not my_sels:
        return JsonResponse({'error': 'Not in this round'}, status=400)

    card_nums = [s.card_number for s in my_sels]
    fee = game_round.entry_fee
    total_refund = fee * len(my_sels)

    with db_transaction.atomic():
        my_sels = list(CardSelection.objects.filter(round=game_round, player=player))
        for s in my_sels:
            s.delete()
        Player.objects.filter(id=player.id).update(coins=F('coins') + total_refund)
        Transaction.objects.create(
            player=player, amount=total_refund,
            transaction_type='draw_refund',
            description=f'Left Arena Round #{game_round.round_number} ({len(my_sels)} cards)'
        )

    _recalc_prize(game_round)
    logger.info(f'ARENA LEAVE: round={game_round.round_number} player={player.telegram_id} cards={card_nums} refunded={total_refund}')
    return JsonResponse({'success': True, 'refunded': total_refund, 'card_numbers': card_nums})


def api_round_state(request, round_id):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    game_round = get_object_or_404(GameRound, id=round_id)
    selections = list(CardSelection.objects.filter(round=game_round).select_related('player'))

    taken_cards = {s.card_number: s.player.first_name for s in selections}
    player_count = len(selections)

    my_sels = [s for s in selections if s.player_id == player.id]
    my_cards = [s.card_number for s in my_sels]
    my_card_grids = []
    my_win = False
    win_pattern = None
    win_cells = None
    win_numbers = None
    win_card = None

    for sel in my_sels:
        numbers = generate_card_by_number(sel.card_number)
        marked = {n for n in game_round.numbers_called if n in numbers}
        my_card_grids.append({
            'card_number': sel.card_number,
            'grid': format_card_grid(numbers, marked),
            'marked': list(marked),
        })
        if game_round.status == 'active':
            result = _check_win(numbers, marked)
            if result and not my_win:
                my_win = True
                win_pattern = result['pattern']
                win_cells = result['cells']
                win_numbers = result['numbers']
                win_card = sel.card_number
        elif game_round.status == 'finished' and game_round.winner_id == player.id:
            result = _check_win(numbers, marked)
            if result and not my_win:
                my_win = True
                win_pattern = result['pattern']
                win_cells = result['cells']
                win_numbers = result['numbers']
                win_card = sel.card_number

    return JsonResponse({
        'status': game_round.status,
        'round_number': game_round.round_number,
        'player_count': player_count,
        'prize_pool': game_round.prize_pool,
        'entry_fee': game_round.entry_fee,
        'taken_cards': taken_cards,
        'my_cards': my_cards,
        'my_card_grids': my_card_grids,
        'called_numbers': game_round.numbers_called,
        'waiting_seconds_left': game_round.waiting_seconds_left,
        'winner_name': game_round.winner.first_name if game_round.winner else None,
        'winner_card': game_round.winner_card_number,
        'winners': game_round.winners_data or [],
        'winner_count': len(game_round.winners_data) if game_round.winners_data else 0,
        'is_winner': my_win,
        'win_pattern': win_pattern,
        'win_cells': win_cells,
        'win_numbers': win_numbers,
        'winning_card': win_card,
        'cancelled': game_round.status == 'finished' and not game_round.winner and not game_round.winners_data and game_round.player_count < 2,
    })


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


def api_card_preview(request, card_number):
    from arena.cards import generate_card_by_number, format_card_grid
    try:
        num = int(card_number)
        if num < 1 or num > 200:
            return JsonResponse({'error': 'Invalid card'}, status=400)
        numbers = generate_card_by_number(num)
        grid = format_card_grid(numbers)
        return JsonResponse({'card_number': num, 'grid': grid})
    except ValueError:
        return JsonResponse({'error': 'Invalid card'}, status=400)


# ═══ Daily Gift ═══


def api_gift_status(request):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    from arena.models import DailyGift
    from django.utils import timezone
    now = timezone.now()

    gift, created = DailyGift.objects.get_or_create(player=player)
    if created:
        gift.cycle_start_at = now
        gift.save(update_fields=['cycle_start_at'])
    elif not gift.cycle_start_at:
        gift.cycle_start_at = now
        gift.save(update_fields=['cycle_start_at'])

    elapsed = (now - gift.cycle_start_at).total_seconds()
    if elapsed >= 86400:
        gift.games_completed = 0
        gift.cycle_start_at = now
        gift.save(update_fields=['games_completed', 'cycle_start_at'])

    can_claim = False
    if gift.games_completed >= 3:
        if not gift.last_claim_at:
            can_claim = True
        else:
            since_claim = (now - gift.last_claim_at).total_seconds()
            if since_claim >= 86400:
                can_claim = True

    gift.refresh_from_db(fields=['games_completed'])
    payload = {
        'games_completed': gift.games_completed,
        'can_claim': can_claim,
        'total_claimed': gift.total_claimed,
    }
    logger.info(
        f'[GIFT DEBUG] Player: {player.telegram_id} '
        f'API response: {payload}'
    )
    return JsonResponse(payload)


@csrf_exempt
@require_POST
def api_gift_claim(request):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    from arena.models import DailyGift
    from django.utils import timezone
    import random as _random
    now = timezone.now()

    gift, _ = DailyGift.objects.get_or_create(player=player)

    if gift.last_claim_at:
        since_claim = (now - gift.last_claim_at).total_seconds()
        if since_claim < 86400:
            return JsonResponse({'error': 'እርስዎ ሽልማቱን አሁን ተጠቅመዋል 🎁 እባክዎ ለ24 ሰዓት ይጠብቁ ከዚያ በኋላ እንደገና ይከፈታል።'}, status=400)
        gift.games_completed = 0
        gift.cycle_start_at = now

    if gift.games_completed < 3:
        return JsonResponse({'error': f'Need 3 games. You have {gift.games_completed}.'}, status=400)

    try:
        box_index = int(request.POST.get('box', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid box'}, status=400)

    if box_index < 1 or box_index > 5:
        return JsonResponse({'error': 'Box must be 1-5'}, status=400)

    all_rewards = DailyGift.ALL_REWARDS[:]
    _random.shuffle(all_rewards)
    boxes = {i + 1: all_rewards[i] for i in range(5)}

    reward = boxes[box_index]
    if reward not in DailyGift.VALID_REWARDS:
        reward = _random.choice(DailyGift.VALID_REWARDS)

    with db_transaction.atomic():
        gift.last_claim_at = now
        gift.games_completed = 0
        gift.cycle_start_at = now
        gift.total_claimed = F('total_claimed') + 1
        if reward == 2:
            gift.reward_2_count = F('reward_2_count') + 1
        elif reward == 3:
            gift.reward_3_count = F('reward_3_count') + 1
        elif reward == 5:
            gift.reward_5_count = F('reward_5_count') + 1
        gift.save()

        Player.objects.filter(id=player.id).update(coins=F('coins') + reward)
        Transaction.objects.create(
            player=player, amount=reward,
            transaction_type='admin_gift',
            description=f'Daily gift box #{box_index} — {reward} Birr'
        )

    return JsonResponse({
        'success': True,
        'reward': reward,
        'boxes': boxes,
    })
