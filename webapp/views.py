import json
import logging
from functools import wraps
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import models as db_models, transaction as db_transaction, close_old_connections
from django.utils import timezone
from users.models import Player
from games.models import GameRoom, BingoCard, GameHistory
from wallets.models import Transaction
from core.utils import generate_bingo_card

logger = logging.getLogger('bingo.room')


def get_player_from_request(request):
    tg_id = request.GET.get('tg_id', '')

    if not tg_id and request.method == 'POST':
        try:
            body = json.loads(request.body)
            tg_id = str(body.get('tg_id', ''))
        except (json.JSONDecodeError, ValueError):
            pass

    if not tg_id:
        tg_id = request.session.get('tg_id', '')

    if not tg_id:
        return None

    try:
        tid = int(tg_id)
        player, created = Player.objects.get_or_create(
            telegram_id=tid,
            defaults={'first_name': 'Player'}
        )
        request.session['tg_id'] = str(tid)
        return player
    except (ValueError, TypeError):
        return None


def require_player(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        player = get_player_from_request(request)
        if not player:
            bot_name = getattr(settings, 'BOT_USERNAME', 'Bingo2BingoBot')
            return render(request, 'webapp/error.html', {
                'message': f'Open from Telegram: /start @{bot_name}',
                'bot_username': bot_name,
            }, status=400)
        request.player = player
        return view_func(request, *args, **kwargs)
    return wrapper


def home(request):
    player = get_player_from_request(request)
    if not player:
        bot_name = getattr(settings, 'BOT_USERNAME', 'Bingo2BingoBot')
        return render(request, 'webapp/error.html', {
            'message': f'Open from Telegram: /start @{bot_name}',
            'bot_username': bot_name,
        })

    if player.games_played > 0:
        win_rate = round(player.wins / player.games_played * 100)
    else:
        win_rate = 0

    can_claim = player.can_claim_daily()
    next_daily = ''
    if not can_claim and player.last_daily_bonus:
        remaining = 86400 - (timezone.now() - player.last_daily_bonus).total_seconds()
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        next_daily = f'{hours}h {mins}m'

    top_players = Player.objects.filter(is_banned=False).order_by('-wins')[:5]

    return render(request, 'webapp/home.html', {
        'player': player,
        'win_rate': win_rate,
        'can_claim': can_claim,
        'next_daily': next_daily,
        'top_players': top_players,
    })


def rooms(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    rooms_qs = list(
        GameRoom.objects.filter(status='waiting', room_type='public')
        .order_by('-created_at')[:20]
    )
    for room in rooms_qs:
        room.active_players = BingoCard.objects.filter(game_room=room).count()

    arena_round = None
    try:
        from arena.models import GameRound as ArenaRound
        from arena.engine import ensure_round_running
        ensure_round_running()
        arena_round = ArenaRound.objects.filter(
            status__in=('waiting', 'active', 'cooldown')
        ).order_by('-created_at').first()
    except Exception:
        pass

    return render(request, 'webapp/rooms.html', {
        'player': player,
        'rooms': rooms_qs,
        'arena_round': arena_round,
    })


def create_room(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    if request.method == 'POST':
        entry_fee = int(request.POST.get('entry_fee', 50))
        max_players = int(request.POST.get('max_players', 2))
        room_type = request.POST.get('room_type', 'public')
        if room_type not in ('public', 'private'):
            room_type = 'public'

        with db_transaction.atomic():
            p = Player.objects.select_for_update().get(id=player.id)
            if p.coins < entry_fee:
                return render(request, 'webapp/create_room.html', {
                    'player': p,
                    'error': f'Need {entry_fee} coins, have {p.coins}'
                })
            p.coins = db_models.F('coins') - entry_fee
            p.save(update_fields=['coins'])

            room = GameRoom.objects.create(
                room_type=room_type,
                entry_fee=entry_fee,
                max_players=max_players,
                prize_pool=entry_fee,
            )
            BingoCard.objects.create(
                player=p,
                game_room=room,
                numbers=generate_bingo_card(),
            )

        Transaction.objects.create(
            player=p, amount=-entry_fee,
            transaction_type='game_entry',
            description=f'Created {room_type} room {room.room_code}'
        )

        logger.info(f'ROOM CREATE: room={room.room_code} type={room_type} creator={p.telegram_id} fee={entry_fee} max={max_players}')

        url = reverse('webapp:room', kwargs={'room_code': room.room_code})
        return redirect(f'{url}?tg_id={p.telegram_id}')

    return render(request, 'webapp/create_room.html', {
        'player': player,
    })


def join_private(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    error = None
    if request.method == 'POST':
        room_code = request.POST.get('room_code', '').strip().upper()
        if not room_code:
            error = 'Enter a room code'
        else:
            try:
                room = GameRoom.objects.get(
                    room_code=room_code, status='waiting', room_type='private'
                )
                url = reverse('webapp:room', kwargs={'room_code': room.room_code})
                return redirect(f'{url}?tg_id={player.telegram_id}')
            except GameRoom.DoesNotExist:
                error = 'Private room not found or already started'

    return render(request, 'webapp/join_private.html', {
        'player': player,
        'error': error,
    })


def room(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    room_data = get_object_or_404(GameRoom, room_code=room_code)

    cards = list(BingoCard.objects.filter(game_room=room_data).select_related('player').order_by('created_at'))
    active_players = len(cards)
    joined = any(c.player_id == player.id for c in cards)

    is_creator = joined and cards and cards[0].player_id == player.id

    logger.info(f'ROOM VIEW: room={room_code} player_tg={player.telegram_id} joined={joined} is_creator={is_creator} active_players={active_players} card_owner_ids={[c.player_id for c in cards]}')

    card_data = None
    card_grid = None
    marked_numbers_json = '[]'

    if joined and room_data.status in ('active', 'finished'):
        try:
            card = next(c for c in cards if c.player_id == player.id)
            card_data = card
            numbers = card.numbers if isinstance(card.numbers, list) else json.loads(card.numbers)
            marked = card.marked if isinstance(card.marked, list) else json.loads(card.marked)
            marked_numbers_json = json.dumps(marked)
            card_grid = [numbers[row * 5:(row + 1) * 5] for row in range(5)]
        except (StopIteration, BingoCard.DoesNotExist):
            pass

    return render(request, 'webapp/room.html', {
        'player': player,
        'room': room_data,
        'cards': cards,
        'active_players': active_players,
        'joined': joined,
        'is_creator': is_creator,
        'card_data': card_data,
        'card_grid': card_grid,
        'marked_numbers_json': marked_numbers_json,
    })


def submit_phone(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    error = None
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        if not phone:
            error = 'Please enter your phone number'
        elif not phone.startswith('09') and not phone.startswith('+251'):
            error = 'Enter valid Ethiopian phone (09... or +251...)'
        elif len(phone) < 10:
            error = 'Phone number too short'
        else:
            player.phone_number = phone
            player.save(update_fields=['phone_number'])
            return redirect('webapp:home')

    return render(request, 'webapp/phone.html', {
        'player': player,
        'error': error,
    })


def leaderboard(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    sort = request.GET.get('sort', 'wins')
    if sort == 'coins':
        players = Player.objects.filter(is_banned=False).order_by('-coins')[:50]
    else:
        players = Player.objects.filter(is_banned=False).order_by('-wins')[:50]

    return render(request, 'webapp/leaderboard.html', {
        'player': player,
        'players': players,
        'sort': sort,
    })


def wallet(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    transactions = Transaction.objects.filter(player=player).exclude(
        transaction_type='house_fee'
    ).order_by('-created_at')[:30]

    return render(request, 'webapp/wallet.html', {
        'player': player,
        'transactions': transactions,
    })


def daily(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    can_claim = player.can_claim_daily()
    next_daily = ''
    if not can_claim and player.last_daily_bonus:
        remaining = 86400 - (timezone.now() - player.last_daily_bonus).total_seconds()
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        next_daily = f'{hours}h {mins}m'

    return render(request, 'webapp/daily.html', {
        'player': player,
        'can_claim': can_claim,
        'next_daily': next_daily,
        'claimed': False,
    })


def claim_daily(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    if not player.can_claim_daily():
        return redirect('webapp:daily')

    with db_transaction.atomic():
        p = Player.objects.select_for_update().get(id=player.id)
        if not p.can_claim_daily():
            return redirect('webapp:daily')
        p.coins = db_models.F('coins') + 100
        p.xp = db_models.F('xp') + 25
        p.last_daily_bonus = timezone.now()
        p.save(update_fields=['coins', 'xp', 'last_daily_bonus'])
        Transaction.objects.create(
            player=p, amount=100,
            transaction_type='daily_bonus',
            description='Daily bonus claimed'
        )

    return render(request, 'webapp/daily.html', {
        'player': p,
        'can_claim': False,
        'claimed': True,
    })


# ═══════════════════════════════════════════
# API Endpoints — Room Lifecycle
# ═══════════════════════════════════════════


@csrf_exempt
@require_POST
def api_join_room(request, room_code):
    player = get_player_from_request(request)
    if not player:
        logger.warning(f'JOIN FAIL: room={room_code} reason=not_authenticated')
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        room = GameRoom.objects.get(room_code=room_code, status='waiting')
    except GameRoom.DoesNotExist:
        logger.warning(f'JOIN FAIL: room={room_code} reason=not_found_or_not_waiting')
        return JsonResponse({'error': 'Room not available'})

    current_count = room.bingo_cards.count()
    logger.info(f'JOIN ATTEMPT: room={room_code} player={player.telegram_id} current_count={current_count} max={room.max_players}')

    if current_count >= room.max_players:
        logger.warning(f'JOIN FAIL: room={room_code} player={player.telegram_id} reason=room_full')
        return JsonResponse({'error': 'Room is full'})

    if BingoCard.objects.filter(player=player, game_room=room).exists():
        logger.warning(f'JOIN FAIL: room={room_code} player={player.telegram_id} reason=already_joined')
        return JsonResponse({'error': 'Already joined'})

    with db_transaction.atomic():
        p = Player.objects.select_for_update().get(id=player.id)
        if p.coins < room.entry_fee:
            logger.warning(f'JOIN FAIL: room={room_code} player={p.telegram_id} reason=insufficient_coins have={p.coins} need={room.entry_fee}')
            return JsonResponse({'error': f'Need {room.entry_fee} coins, have {p.coins}'})

        p.coins = db_models.F('coins') - room.entry_fee
        p.save(update_fields=['coins'])

        card = BingoCard.objects.create(
            player=p, game_room=room, numbers=generate_bingo_card()
        )
        room.prize_pool = db_models.F('prize_pool') + room.entry_fee
        room.save(update_fields=['prize_pool'])

    Transaction.objects.create(
        player=p, amount=-room.entry_fee,
        transaction_type='game_entry', description=f'Joined room {room_code}'
    )

    new_count = current_count + 1
    logger.info(f'JOIN OK: room={room_code} player={p.telegram_id} new_count={new_count}/{room.max_players} card_id={card.id}')

    return JsonResponse({
        'success': True,
        'player_count': new_count,
        'max_players': room.max_players,
    })


@csrf_exempt
@require_POST
def api_leave_room(request, room_code):
    player = get_player_from_request(request)
    if not player:
        logger.warning(f'LEAVE FAIL: room={room_code} reason=not_authenticated')
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        card = BingoCard.objects.select_related('game_room').get(
            player=player, game_room__room_code=room_code,
            game_room__status='waiting'
        )
    except BingoCard.DoesNotExist:
        logger.warning(f'LEAVE FAIL: room={room_code} player={player.telegram_id} reason=not_in_room')
        return JsonResponse({'error': 'Cannot leave'})

    room = card.game_room
    fee = room.entry_fee

    with db_transaction.atomic():
        p = Player.objects.select_for_update().get(id=player.id)
        p.coins = db_models.F('coins') + fee
        p.save(update_fields=['coins'])
        room.prize_pool = db_models.F('prize_pool') - fee
        room.save(update_fields=['prize_pool'])
        card.delete()

        remaining = BingoCard.objects.filter(game_room=room).count()
        if remaining == 0:
            room.status = 'finished'
            room.finished_at = timezone.now()
            room.save(update_fields=['status', 'finished_at'])
            logger.info(f'ROOM CLOSED: room={room_code} reason=all_players_left')

    Transaction.objects.create(
        player=p, amount=fee,
        transaction_type='deposit', description=f'Refund from leaving room {room_code}'
    )

    logger.info(f'LEAVE OK: room={room_code} player={p.telegram_id} remaining={remaining}')

    return JsonResponse({
        'success': True,
        'room_closed': remaining == 0,
    })


@csrf_exempt
@require_POST
def api_start_game(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    room = get_object_or_404(GameRoom, room_code=room_code)
    if room.status != 'waiting':
        return JsonResponse({'error': 'Game already started'})

    cards = list(BingoCard.objects.filter(game_room=room))
    if len(cards) < room.max_players:
        logger.warning(f'START FAIL: room={room_code} player={player.telegram_id} reason=not_full count={len(cards)}/{room.max_players}')
        return JsonResponse({'error': f'Need {room.max_players} players. Currently {len(cards)}/{room.max_players}.'})

    room.status = 'active'
    room.started_at = timezone.now()
    room.save(update_fields=['status', 'started_at'])

    logger.info(f'GAME START: room={room_code} players={len(cards)} starter={player.telegram_id}')

    from .engine import start_game_thread
    start_game_thread(room_code)

    return JsonResponse({'success': True})


def api_room_info(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        room = GameRoom.objects.get(room_code=room_code)
    except GameRoom.DoesNotExist:
        return JsonResponse({'error': 'Room not found'}, status=404)

    cards = list(BingoCard.objects.filter(game_room=room).select_related('player').order_by('created_at'))
    player_list = []
    for c in cards:
        player_list.append({
            'telegram_id': c.player.telegram_id,
            'first_name': c.player.first_name,
        })

    is_creator = any(c.player_id == player.id for c in cards) and cards and cards[0].player_id == player.id

    return JsonResponse({
        'status': room.status,
        'room_code': room.room_code,
        'player_count': len(cards),
        'max_players': room.max_players,
        'entry_fee': room.entry_fee,
        'prize_pool': room.prize_pool,
        'players': player_list,
        'winner_name': room.winner.first_name if room.winner else None,
        'is_creator': is_creator,
    })


def _compute_winning_cells(numbers_list, marked):
    winning_cells = []
    size = 5
    marked_set = set(marked)
    free_idx = 12

    def is_marked(idx):
        return idx == free_idx or numbers_list[idx] in marked_set

    def cell_num(idx):
        return 0 if idx == free_idx else numbers_list[idx]

    for i in range(size):
        row_nums = [cell_num(i * size + j) for j in range(size)]
        if all(is_marked(i * size + j) for j in range(size)):
            winning_cells.extend(row_nums)
        col_nums = [cell_num(j * size + i) for j in range(size)]
        if all(is_marked(j * size + i) for j in range(size)):
            winning_cells.extend(col_nums)

    diag1 = [cell_num(i * size + i) for i in range(size)]
    if all(is_marked(i * size + i) for i in range(size)):
        winning_cells.extend(diag1)
    diag2 = [cell_num(i * size + (size - 1 - i)) for i in range(size)]
    if all(is_marked(i * size + (size - 1 - i)) for i in range(size)):
        winning_cells.extend(diag2)

    return list(set(winning_cells))


def _get_card_state(card, room):
    marked = card.marked if isinstance(card.marked, list) else []
    numbers_list = card.numbers if isinstance(card.numbers, list) else []
    history = GameHistory.objects.filter(game_room=room).first()
    called = history.numbers_called if history and history.numbers_called else []
    is_win = card.check_win()
    winning_cells = _compute_winning_cells(numbers_list, marked) if is_win else []
    return marked, numbers_list, called, is_win, winning_cells


def api_room_state(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    room = get_object_or_404(GameRoom, room_code=room_code)

    try:
        card = BingoCard.objects.get(player=player, game_room=room)
    except BingoCard.DoesNotExist:
        return JsonResponse({
            'status': room.status,
            'marked': [],
            'called_numbers': [],
            'winning_cells': [],
            'current_number': None,
            'next_in': 2,
            'winner_name': room.winner.first_name if room.winner else None,
            'prize': room.prize_pool,
        })

    marked, numbers_list, called, is_win, winning_cells = _get_card_state(card, room)

    if room.status == 'waiting':
        return JsonResponse({
            'status': room.status,
            'marked': marked,
            'called_numbers': called,
            'winning_cells': [],
            'current_number': None,
            'next_in': 2,
        })

    if is_win:
        return JsonResponse({
            'status': 'finished',
            'marked': marked,
            'called_numbers': called,
            'winning_cells': winning_cells,
            'current_number': called[-1] if called else None,
            'next_in': 0,
            'winner_name': player.first_name,
            'prize': room.prize_pool,
        })

    if room.status == 'finished':
        marked = card.marked if isinstance(card.marked, list) else []
        numbers_list = card.numbers if isinstance(card.numbers, list) else []
        marked_set = set(marked)
        size = 5
        free_idx = 12
        max_line = 0
        for i in range(size):
            row_filled = sum(1 for j in range(size) if (i*size+j)==free_idx or numbers_list[i*size+j] in marked_set)
            col_filled = sum(1 for j in range(size) if (j*size+i)==free_idx or numbers_list[j*size+i] in marked_set)
            if row_filled > max_line: max_line = row_filled
            if col_filled > max_line: max_line = col_filled
        diag1 = sum(1 for i in range(size) if (i*size+i)==free_idx or numbers_list[i*size+i] in marked_set)
        diag2 = sum(1 for i in range(size) if (i*size+size-1-i)==free_idx or numbers_list[i*size+size-1-i] in marked_set)
        if diag1 > max_line: max_line = diag1
        if diag2 > max_line: max_line = diag2
        closeness = min(100, int(max_line / size * 100))
        return JsonResponse({
            'status': 'finished',
            'marked': marked,
            'called_numbers': called,
            'winning_cells': [],
            'current_number': None,
            'next_in': 0,
            'winner_name': room.winner.first_name if room.winner else None,
            'prize': room.prize_pool,
            'closeness': closeness,
            'draw': not room.winner,
        })

    winning_cells = _compute_winning_cells(numbers_list, marked)

    return JsonResponse({
        'status': 'active',
        'marked': marked,
        'called_numbers': called,
        'winning_cells': winning_cells,
        'current_number': called[-1] if called else None,
        'next_in': 2,
    })
