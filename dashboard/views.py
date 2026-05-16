import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import models as db_models, transaction as db_transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone
from users.models import Player
from games.models import GameRoom, BingoCard, GameHistory
from wallets.models import Transaction
from dashboard.models import AdminLog
from dashboard.auth import admin_required

logger = logging.getLogger('bingo.dashboard')


def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('dashboard:overview')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user and user.is_staff:
            auth_login(request, user)
            return redirect('dashboard:overview')
        return render(request, 'dashboard/login.html', {'error': 'Invalid credentials or not staff.'})
    return render(request, 'dashboard/login.html')


def logout_view(request):
    auth_logout(request)
    return redirect('dashboard:login')


@admin_required
def overview(request):
    total_players = Player.objects.count()
    active_rooms = GameRoom.objects.filter(status='waiting').count()
    active_games = GameRoom.objects.filter(status='active').count()
    finished_games = GameRoom.objects.filter(status='finished').count()
    total_coins_issued = Transaction.objects.filter(
        transaction_type='deposit'
    ).aggregate(s=Sum('amount'))['s'] or 0
    total_coins_won = Transaction.objects.filter(
        transaction_type='game_win'
    ).aggregate(s=Sum('amount'))['s'] or 0

    recent_rooms = list(GameRoom.objects.select_related('winner')
        .annotate(pc=Count('bingo_cards'))
        .order_by('-created_at')[:10])

    recent_logs = list(AdminLog.objects.select_related('admin_user', 'target_player')
        .order_by('-created_at')[:20])

    top_winners = list(Player.objects.filter(is_banned=False)
        .order_by('-wins')[:5])

    return render(request, 'dashboard/overview.html', {
        'total_players': total_players,
        'active_rooms': active_rooms,
        'active_games': active_games,
        'finished_games': finished_games,
        'total_coins_issued': total_coins_issued,
        'total_coins_won': total_coins_won,
        'recent_rooms': recent_rooms,
        'recent_logs': recent_logs,
        'top_winners': top_winners,
    })


@admin_required
def players(request):
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', 'all')

    players_qs = Player.objects.all()
    if search:
        players_qs = players_qs.filter(
            Q(first_name__icontains=search) |
            Q(username__icontains=search) |
            Q(telegram_id__icontains=search)
        )
    if status_filter == 'banned':
        players_qs = players_qs.filter(is_banned=True)
    elif status_filter == 'active':
        players_qs = players_qs.filter(is_banned=False)

    players_list = list(players_qs.order_by('-coins')[:100])

    return render(request, 'dashboard/players.html', {
        'players': players_list,
        'search': search,
        'status_filter': status_filter,
    })


@admin_required
def rooms(request):
    status_filter = request.GET.get('status', 'all')

    rooms_qs = GameRoom.objects.annotate(pc=Count('bingo_cards')).select_related('winner')
    if status_filter != 'all':
        rooms_qs = rooms_qs.filter(status=status_filter)

    rooms_list = list(rooms_qs.order_by('-created_at')[:50])

    return render(request, 'dashboard/rooms.html', {
        'rooms': rooms_list,
        'status_filter': status_filter,
    })


@admin_required
def room_detail(request, room_code):
    room = get_object_or_404(
        GameRoom.objects.annotate(pc=Count('bingo_cards')).select_related('winner'),
        room_code=room_code
    )
    cards = list(BingoCard.objects.filter(game_room=room).select_related('player'))
    history = GameHistory.objects.filter(game_room=room).first()

    return render(request, 'dashboard/room_detail.html', {
        'room': room,
        'cards': cards,
        'history': history,
    })


@admin_required
def live_games(request):
    active_rooms = list(
        GameRoom.objects.filter(status='active')
        .annotate(pc=Count('bingo_cards'))
        .order_by('-started_at')[:20]
    )
    waiting_rooms = list(
        GameRoom.objects.filter(status='waiting')
        .annotate(pc=Count('bingo_cards'))
        .order_by('-created_at')[:20]
    )

    if request.GET.get('fragment'):
        return render(request, 'dashboard/_live_rows_wrapper.html', {
            'active_rooms': active_rooms,
            'waiting_rooms': waiting_rooms,
        })

    return render(request, 'dashboard/live.html', {
        'active_rooms': active_rooms,
        'waiting_rooms': waiting_rooms,
    })


@admin_required
def transactions(request):
    search = request.GET.get('search', '')
    tx_qs = Transaction.objects.select_related('player').order_by('-created_at')
    if search:
        tx_qs = tx_qs.filter(
            Q(player__first_name__icontains=search) |
            Q(player__username__icontains=search) |
            Q(description__icontains=search)
        )
    tx_list = list(tx_qs[:200])
    return render(request, 'dashboard/transactions.html', {
        'transactions': tx_list,
        'search': search,
    })


@admin_required
def logs(request):
    logs_list = list(AdminLog.objects.select_related('admin_user', 'target_player', 'target_room')
        .order_by('-created_at')[:200])
    return render(request, 'dashboard/logs.html', {
        'logs': logs_list,
    })


# ═══ API Endpoints ═══


@csrf_exempt
@require_POST
@admin_required
def api_add_coins(request, player_id):
    amount = int(request.POST.get('amount', 0))
    reason = request.POST.get('reason', 'Admin gift')
    if amount <= 0:
        return JsonResponse({'error': 'Amount must be positive'}, status=400)

    player = get_object_or_404(Player, id=player_id)
    player.coins = db_models.F('coins') + amount
    player.save(update_fields=['coins'])

    Transaction.objects.create(
        player=player, amount=amount,
        transaction_type='admin_gift',
        description=f'Admin: {reason}'
    )
    AdminLog.objects.create(
        admin_user=request.user, action='coin_add',
        target_player=player, amount=amount,
        detail=reason
    )
    player.refresh_from_db()
    logger.info(f'ADMIN: {request.user} added {amount} coins to player {player.telegram_id} reason={reason}')
    return JsonResponse({'success': True, 'new_balance': player.coins})


@csrf_exempt
@require_POST
@admin_required
def api_deduct_coins(request, player_id):
    amount = int(request.POST.get('amount', 0))
    reason = request.POST.get('reason', 'Admin deduction')
    if amount <= 0:
        return JsonResponse({'error': 'Amount must be positive'}, status=400)

    player = get_object_or_404(Player, id=player_id)
    with db_transaction.atomic():
        p = Player.objects.select_for_update().get(id=player_id)
        if p.coins < amount:
            return JsonResponse({'error': f'Player only has {p.coins} coins'}, status=400)
        p.coins = db_models.F('coins') - amount
        p.save(update_fields=['coins'])

    Transaction.objects.create(
        player=p, amount=-amount,
        transaction_type='withdrawal',
        description=f'Admin: {reason}'
    )
    AdminLog.objects.create(
        admin_user=request.user, action='coin_deduct',
        target_player=player, amount=amount,
        detail=reason
    )
    p.refresh_from_db()
    logger.info(f'ADMIN: {request.user} deducted {amount} coins from player {p.telegram_id}')
    return JsonResponse({'success': True, 'new_balance': p.coins})


@csrf_exempt
@require_POST
@admin_required
def api_reset_coins(request, player_id):
    player = get_object_or_404(Player, id=player_id)
    old = player.coins
    player.coins = 0
    player.save(update_fields=['coins'])

    AdminLog.objects.create(
        admin_user=request.user, action='coin_reset',
        target_player=player,
        detail=f'Reset from {old} to 0'
    )
    logger.info(f'ADMIN: {request.user} reset coins for player {player.telegram_id} from {old}')
    return JsonResponse({'success': True, 'new_balance': player.coins})


@csrf_exempt
@require_POST
@admin_required
def api_ban_player(request, player_id):
    player = get_object_or_404(Player, id=player_id)
    player.is_banned = not player.is_banned
    player.save(update_fields=['is_banned'])
    action = 'player_ban' if player.is_banned else 'player_unban'

    AdminLog.objects.create(
        admin_user=request.user, action=action,
        target_player=player,
        detail=f'{"Banned" if player.is_banned else "Unbanned"}'
    )
    logger.info(f'ADMIN: {request.user} {"banned" if player.is_banned else "unbanned"} player {player.telegram_id}')
    return JsonResponse({'success': True, 'is_banned': player.is_banned})


@csrf_exempt
@require_POST
@admin_required
def api_kick_player(request, player_id, room_code):
    player = get_object_or_404(Player, id=player_id)
    room = get_object_or_404(GameRoom, room_code=room_code)

    card = BingoCard.objects.filter(player=player, game_room=room).first()
    if card:
        fee = room.entry_fee
        with db_transaction.atomic():
            p = Player.objects.select_for_update().get(id=player_id)
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

        Transaction.objects.create(
            player=p, amount=fee, transaction_type='deposit',
            description=f'Admin kick from room {room_code}'
        )
        AdminLog.objects.create(
            admin_user=request.user, action='player_kick',
            target_player=player, target_room=room,
            detail=f'Kicked from room {room_code}'
        )
        logger.info(f'ADMIN: {request.user} kicked player {player.telegram_id} from room {room_code}')

    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@admin_required
def api_force_close_room(request, room_code):
    room = get_object_or_404(GameRoom, room_code=room_code)
    room.status = 'finished'
    room.finished_at = timezone.now()
    room.save(update_fields=['status', 'finished_at'])

    BingoCard.objects.filter(game_room=room).delete()

    AdminLog.objects.create(
        admin_user=request.user, action='room_close',
        target_room=room, detail=f'Force closed room {room_code}'
    )
    logger.info(f'ADMIN: {request.user} force closed room {room_code}')
    return JsonResponse({'success': True})


@admin_required
def api_room_live_state(request, room_code):
    room = get_object_or_404(GameRoom, room_code=room_code)
    cards = list(BingoCard.objects.filter(game_room=room).select_related('player'))
    history = GameHistory.objects.filter(game_room=room).first()

    return JsonResponse({
        'status': room.status,
        'room_code': room.room_code,
        'player_count': len(cards),
        'max_players': room.max_players,
        'prize_pool': room.prize_pool,
        'players': [{'first_name': c.player.first_name, 'telegram_id': c.player.telegram_id} for c in cards],
        'called_numbers': history.numbers_called if history else [],
        'winner_name': room.winner.first_name if room.winner else None,
        'started_at': room.started_at.isoformat() if room.started_at else None,
        'game_mode': room.game_mode,
        'game_state': room.game_state,
    })


# ═══ Game Control Endpoints (Admin Only) ═══


@csrf_exempt
@require_POST
@admin_required
def api_game_next_number(request, room_code):
    from webapp.engine import trigger_next_number
    room = get_object_or_404(GameRoom, room_code=room_code)
    if room.status != 'active':
        return JsonResponse({'error': 'Game not active'}, status=400)
    if room.game_mode != 'manual':
        return JsonResponse({'error': 'Switch to manual mode first'}, status=400)

    ok = trigger_next_number(room_code)
    if not ok:
        return JsonResponse({'error': 'Game engine not running for this room'}, status=400)

    room.refresh_from_db()
    AdminLog.objects.create(
        admin_user=request.user, action='game_end',
        target_room=room, detail=f'Manual next number triggered'
    )
    logger.info(f'ADMIN: {request.user} triggered next number in room {room_code}')
    return JsonResponse({'success': True, 'game_state': room.game_state})


@csrf_exempt
@require_POST
@admin_required
def api_game_call_number(request, room_code):
    try:
        number = int(request.POST.get('number', ''))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid number'}, status=400)

    from webapp.engine import call_specific_number

    ok, error = call_specific_number(room_code, number)
    if not ok:
        logger.warning(f'ADMIN CALL FAIL: room={room_code} number={number} error={error}')
        return JsonResponse({'error': error}, status=400)

    room = get_object_or_404(GameRoom, room_code=room_code)
    AdminLog.objects.create(
        admin_user=request.user, action='game_end',
        target_room=room,
        detail=f'Manual call: number {number}'
    )
    logger.info(f'ADMIN: {request.user} called number {number} in room {room_code}')
    return JsonResponse({
        'success': True,
        'number': number,
        'game_state': room.game_state,
    })


@csrf_exempt
@require_POST
@admin_required
def api_game_pause(request, room_code):
    from webapp.engine import pause_game
    room = get_object_or_404(GameRoom, room_code=room_code)
    if room.status != 'active':
        return JsonResponse({'error': 'Game not active'}, status=400)

    pause_game(room_code)
    room.game_state = {**(room.game_state or {}), 'paused': True}
    room.save(update_fields=['game_state'])

    logger.info(f'ADMIN: {request.user} paused game room {room_code}')
    return JsonResponse({'success': True, 'paused': True})


@csrf_exempt
@require_POST
@admin_required
def api_game_resume(request, room_code):
    from webapp.engine import resume_game
    room = get_object_or_404(GameRoom, room_code=room_code)
    if room.status != 'active':
        return JsonResponse({'error': 'Game not active'}, status=400)

    resume_game(room_code)
    room.game_state = {**(room.game_state or {}), 'paused': False}
    room.save(update_fields=['game_state'])

    logger.info(f'ADMIN: {request.user} resumed game room {room_code}')
    return JsonResponse({'success': True, 'paused': False})


@csrf_exempt
@require_POST
@admin_required
def api_game_set_mode(request, room_code):
    mode = request.POST.get('mode', 'auto')
    if mode not in ('auto', 'manual'):
        return JsonResponse({'error': 'Invalid mode'}, status=400)

    from webapp.engine import switch_game_mode
    room = get_object_or_404(GameRoom, room_code=room_code)
    if room.status != 'active':
        return JsonResponse({'error': 'Game not active'}, status=400)

    switch_game_mode(room_code, mode)

    AdminLog.objects.create(
        admin_user=request.user, action='game_end',
        target_room=room, detail=f'Mode set to {mode}'
    )
    logger.info(f'ADMIN: {request.user} set mode {mode} for room {room_code}')
    return JsonResponse({'success': True, 'game_mode': mode})
