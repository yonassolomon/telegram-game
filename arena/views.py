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

    selected_card = None
    if current:
        sel = CardSelection.objects.filter(round=current, player=player).first()
        if sel:
            selected_card = sel.card_number

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
        'selected_card': selected_card,
        'can_claim_daily': can_claim,
        'next_daily': next_daily,
        'next_daily_seconds': next_daily_seconds,
        'taken_cards_json': json.dumps(taken_cards),
        'my_card_grid': selected_card and _get_card_grid(selected_card, set()) or None,
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

    if card_num < 1 or card_num > 100:
        return JsonResponse({'error': 'Card must be 1-100'}, status=400)

    game_round = get_object_or_404(GameRound, id=round_id)

    if game_round.status != 'waiting':
        return JsonResponse({'error': 'Card selection is closed. Game already started.'}, status=400)

    with db_transaction.atomic():
        existing_player = CardSelection.objects.select_for_update().filter(round=game_round, player=player).first()
        if existing_player:
            old_card = existing_player.card_number
            existing_player.card_number = card_num
            existing_player.save(update_fields=['card_number'])
            logger.info(f'CARD CHANGED: round={game_round.round_number} player={player.telegram_id} {old_card}→{card_num}')
            return JsonResponse({'success': True, 'card_number': card_num, 'changed': True, 'old_card': old_card})

        p = Player.objects.select_for_update().get(id=player.id)
        if p.coins < game_round.entry_fee:
            return JsonResponse({'error': f'❌ Insufficient coins. Need {game_round.entry_fee}, have {p.coins}.'}, status=400)

        existing_card = CardSelection.objects.filter(round=game_round, card_number=card_num).first()
        if existing_card:
            return JsonResponse({'error': f'Card {card_num} already chosen by another player'}, status=409)

        CardSelection.objects.create(round=game_round, player=p, card_number=card_num)
        p.coins = F('coins') - game_round.entry_fee
        p.save(update_fields=['coins'])

        from core.utils import calculate_prize
        total_pot = game_round.entry_fee * CardSelection.objects.filter(round=game_round).count()
        winner_prize, _ = calculate_prize(total_pot)
        GameRound.objects.filter(id=game_round.id).update(prize_pool=winner_prize)

        Transaction.objects.create(
            player=p, amount=-game_round.entry_fee,
            transaction_type='game_entry',
            description=f'Arena Round #{game_round.round_number} entry'
        )

    logger.info(f'CARD SELECTED: round={game_round.round_number} player={player.telegram_id} card={card_num} fee={game_round.entry_fee}')

    return JsonResponse({'success': True, 'card_number': card_num})


@csrf_exempt
@require_POST
def api_leave_arena(request, round_id):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    game_round = get_object_or_404(GameRound, id=round_id)
    if game_round.status != 'waiting':
        return JsonResponse({'error': 'Game already started. Cannot leave.'}, status=400)

    sel = CardSelection.objects.filter(round=game_round, player=player).first()
    if not sel:
        return JsonResponse({'error': 'Not in this round'}, status=400)

    card_num = sel.card_number
    fee = game_round.entry_fee

    with db_transaction.atomic():
        sel.delete()
        Player.objects.filter(id=player.id).update(coins=F('coins') + fee)
        Transaction.objects.create(
            player=player, amount=fee,
            transaction_type='draw_refund',
            description=f'Left Arena Round #{game_round.round_number} before start'
        )
        from core.utils import calculate_prize
        total_pot = game_round.entry_fee * CardSelection.objects.filter(round=game_round).count()
        winner_prize, _ = calculate_prize(total_pot)
        GameRound.objects.filter(id=game_round.id).update(prize_pool=winner_prize)

    logger.info(f'ARENA LEAVE: round={game_round.round_number} player={player.telegram_id} card={card_num} refunded={fee}')
    return JsonResponse({'success': True, 'refunded': fee, 'card_number': card_num})


def api_round_state(request, round_id):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    game_round = get_object_or_404(GameRound, id=round_id)
    selections = list(CardSelection.objects.filter(round=game_round).select_related('player'))

    taken_cards = {s.card_number: s.player.first_name for s in selections}
    player_count = len(selections)

    my_card = None
    my_card_grid = None
    my_marked = set()

    sel = next((s for s in selections if s.player_id == player.id), None)
    if sel:
        my_card = sel.card_number
        numbers = generate_card_by_number(my_card)
        my_marked = {n for n in game_round.numbers_called if n in numbers}
        my_card_grid = format_card_grid(numbers, my_marked)

    my_win = False
    win_pattern = None
    win_cells = None
    win_numbers = None
    if my_card:
        numbers = generate_card_by_number(my_card)
        if game_round.status == 'active':
            result = _check_win(numbers, my_marked)
            if result:
                my_win = True
                win_pattern = result['pattern']
                win_cells = result['cells']
                win_numbers = result['numbers']
        elif game_round.status == 'finished' and game_round.winner_id == player.id:
            marked_set = {n for n in game_round.numbers_called if n in numbers}
            result = _check_win(numbers, marked_set)
            if result:
                my_win = True
                win_pattern = result['pattern']
                win_cells = result['cells']
                win_numbers = result['numbers']

    return JsonResponse({
        'status': game_round.status,
        'round_number': game_round.round_number,
        'player_count': player_count,
        'prize_pool': game_round.prize_pool,
        'entry_fee': game_round.entry_fee,
        'taken_cards': taken_cards,
        'my_card': my_card,
        'my_card_grid': my_card_grid,
        'my_marked': list(my_marked),
        'called_numbers': game_round.numbers_called,
        'waiting_seconds_left': game_round.waiting_seconds_left,
        'winner_name': game_round.winner.first_name if game_round.winner else None,
        'winner_card': game_round.winner_card_number,
        'is_winner': my_win,
        'win_pattern': win_pattern,
        'win_cells': win_cells,
        'win_numbers': win_numbers,
        'cancelled': game_round.status == 'finished' and not game_round.winner and game_round.player_count < 2,
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
        if num < 1 or num > 100:
            return JsonResponse({'error': 'Invalid card'}, status=400)
        numbers = generate_card_by_number(num)
        grid = format_card_grid(numbers)
        return JsonResponse({'card_number': num, 'grid': grid})
    except ValueError:
        return JsonResponse({'error': 'Invalid card'}, status=400)
