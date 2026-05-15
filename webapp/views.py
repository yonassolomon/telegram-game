import json
import hmac
import hashlib
from functools import wraps
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import models as db_models, transaction as db_transaction
from django.utils import timezone
from django.db.models import Count
from users.models import Player
from games.models import GameRoom, BingoCard, GameHistory
from wallets.models import Transaction
from referrals.models import Referral
from core.utils import generate_bingo_card, format_card

import logging
logger = logging.getLogger(__name__)


def get_player_from_request(request):
    tg_id = request.GET.get('tg_id', '')

    if not tg_id and request.method == 'POST':
        try:
            body = json.loads(request.body)
            tg_id = str(body.get('tg_id', ''))
        except (json.JSONDecodeError, ValueError):
            tg_id = request.POST.get('tg_id', '')

    if not tg_id:
        tg_id = request.session.get('tg_id', '')

    if not tg_id:
        tg_id = request.session.get('tg_id', '')

    init_data = request.GET.get('tgWebAppData', '') or request.GET.get('initData', '')
    if not tg_id and init_data:
        try:
            from urllib.parse import unquote
            decoded = unquote(init_data)
            pairs = {}
            for pair in decoded.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    pairs[k] = v
            user_json = pairs.get('user', '{}')
            user = json.loads(user_json)
            tg_id = str(user.get('id', ''))
        except Exception:
            pass

    if not tg_id:
        tg_id = request.GET.get('user_id', '')

    if not tg_id:
        return None

    try:
        tid = int(tg_id)
        request.session['tg_id'] = str(tid)
        player, created = Player.objects.get_or_create(
            telegram_id=tid,
            defaults={'first_name': 'Player'}
        )
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
        return render(request, 'webapp/error.html', {
            'message': 'Open from Telegram: /start @Bingo2BingoBot'
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

    rooms_qs = list(GameRoom.objects.filter(status='waiting').order_by('-created_at')[:20])
    for room in rooms_qs:
        room.active_players = BingoCard.objects.filter(game_room=room).count()

    return render(request, 'webapp/rooms.html', {
        'player': player,
        'rooms': rooms_qs,
    })


def create_room(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    if request.method == 'POST':
        entry_fee = int(request.POST.get('entry_fee', 50))
        max_players = int(request.POST.get('max_players', 2))

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
            description=f'Created room {room.room_code}'
        )

        return redirect('webapp:room', room_code=room.room_code)

    return render(request, 'webapp/create_room.html', {
        'player': player,
    })


def room(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    room_data = get_object_or_404(GameRoom, room_code=room_code)

    cards = list(BingoCard.objects.filter(game_room=room_data).select_related('player'))
    active_players = len(cards)
    joined = BingoCard.objects.filter(
        player=player, game_room=room_data
    ).exists()

    card_data = None
    card_grid = None
    marked_numbers_json = '[]'

    if joined and room_data.status in ('active', 'finished'):
        try:
            card = BingoCard.objects.get(player=player, game_room=room_data)
            card_data = card
            numbers = card.numbers if isinstance(card.numbers, list) else json.loads(card.numbers)
            marked = card.marked if isinstance(card.marked, list) else json.loads(card.marked)
            marked_numbers_json = json.dumps(marked)
            card_grid = []
            for row in range(5):
                card_grid.append(numbers[row * 5:(row + 1) * 5])
        except BingoCard.DoesNotExist:
            pass

    return render(request, 'webapp/room.html', {
        'player': player,
        'room': room_data,
        'cards': cards,
        'active_players': active_players,
        'joined': joined,
        'card_data': card_data,
        'card_grid': card_grid,
        'marked_numbers_json': marked_numbers_json,
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

    transactions = Transaction.objects.filter(player=player).order_by('-created_at')[:30]

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


# ═══ API Endpoints ═══


@csrf_exempt
@require_POST
def api_join_room(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        room = GameRoom.objects.get(room_code=room_code, status='waiting')
    except GameRoom.DoesNotExist:
        return JsonResponse({'error': 'Room not available'})

    if room.bingo_cards.count() >= room.max_players:
        return JsonResponse({'error': 'Room is full'})

    if BingoCard.objects.filter(player=player, game_room=room).exists():
        return JsonResponse({'error': 'Already joined'})

    with db_transaction.atomic():
        p = Player.objects.select_for_update().get(id=player.id)
        if p.coins < room.entry_fee:
            return JsonResponse({'error': f'Need {room.entry_fee} coins, have {p.coins}'})
        p.coins = db_models.F('coins') - room.entry_fee
        p.save(update_fields=['coins'])
        BingoCard.objects.create(player=p, game_room=room, numbers=generate_bingo_card())
        room.prize_pool = db_models.F('prize_pool') + room.entry_fee
        room.save(update_fields=['prize_pool'])

    Transaction.objects.create(
        player=p, amount=-room.entry_fee,
        transaction_type='game_entry', description=f'Joined room {room_code}'
    )

    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
def api_leave_room(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    try:
        card = BingoCard.objects.select_related('game_room').get(
            player=player, game_room__room_code=room_code,
            game_room__status='waiting'
        )
    except BingoCard.DoesNotExist:
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

    Transaction.objects.create(
        player=p, amount=fee,
        transaction_type='deposit', description=f'Refund from leaving room {room_code}'
    )

    return JsonResponse({'success': True})


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
    if len(cards) < 2:
        return JsonResponse({'error': 'Need at least 2 players'})

    room.status = 'active'
    room.started_at = timezone.now()
    room.save(update_fields=['status', 'started_at'])

    from .engine import start_game_thread
    start_game_thread(room_code)

    return JsonResponse({'success': True})


def api_room_state(request, room_code):
    player = get_player_from_request(request)
    if not player:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    room = get_object_or_404(GameRoom, room_code=room_code)

    if room.status in ('waiting', 'finished'):
        return JsonResponse({
            'status': room.status,
            'winner_name': room.winner.first_name if room.winner else None,
            'prize': room.prize_pool,
        })

    if room.status == 'active':
        try:
            card = BingoCard.objects.get(player=player, game_room=room)
        except BingoCard.DoesNotExist:
            return JsonResponse({'status': 'active', 'marked': []})

        marked = card.marked if isinstance(card.marked, list) else []
        history = GameHistory.objects.filter(game_room=room).first()
        called = history.numbers_called if history and history.numbers_called else []

        if card.check_win():
            return JsonResponse({
                'status': 'finished',
                'winner_name': player.first_name,
                'prize': room.prize_pool,
                'marked': marked,
                'called_numbers': called,
            })

        winning_cells = []
        numbers_list = card.numbers if isinstance(card.numbers, list) else []
        size = 5
        marked_set = set(marked)
        for i in range(size):
            row_nums = [numbers_list[i * size + j] for j in range(size)]
            if all(n in marked_set for n in row_nums):
                winning_cells.extend(row_nums)
            col_nums = [numbers_list[j * size + i] for j in range(size)]
            if all(n in marked_set for n in col_nums):
                winning_cells.extend(col_nums)
        diag1 = [numbers_list[i * size + i] for i in range(size)]
        if all(n in marked_set for n in diag1):
            winning_cells.extend(diag1)
        diag2 = [numbers_list[i * size + (size - 1 - i)] for i in range(size)]
        if all(n in marked_set for n in diag2):
            winning_cells.extend(diag2)

        return JsonResponse({
            'status': 'active',
            'marked': marked,
            'called_numbers': called,
            'winning_cells': list(set(winning_cells)),
            'current_number': called[-1] if called else None,
            'next_in': 2,
        })

    return JsonResponse({'status': 'unknown'})
