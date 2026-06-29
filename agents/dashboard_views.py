from functools import wraps
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, hashers
from django.contrib.auth.models import User
from django.db.models import Sum
from agents.models import AgentProfile, CommissionLedger, GameEntryLog, AgentRequest
from users.models import Player


def agent_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('agents:login')
        if request.user.is_staff:
            return redirect('dashboard:overview')
        try:
            agent_profile = request.user.agent_profile
            request.agent_profile = agent_profile
            request.agent_player = agent_profile.player
        except AgentProfile.DoesNotExist:
            return render(request, 'agents/login.html', {'error': 'No agent account found.'})
        return view_func(request, *args, **kwargs)
    return wrapper


def login_view(request):
    if request.user.is_authenticated and not request.user.is_staff:
        try:
            request.user.agent_profile
            return redirect('agents:overview')
        except AgentProfile.DoesNotExist:
            pass
    error = None
    success = request.GET.get('approved', '')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user and not user.is_staff:
            try:
                user.agent_profile
                auth_login(request, user)
                return redirect('agents:overview')
            except AgentProfile.DoesNotExist:
                pass
        if AgentRequest.objects.filter(username=username, status='pending').exists():
            error = 'Your agent request is still pending admin approval.'
        else:
            error = 'Invalid credentials or not an approved agent.'
    return render(request, 'agents/login.html', {'error': error, 'success': success})


def logout_view(request):
    auth_logout(request)
    return redirect('agents:login')


def register_view(request):
    if request.user.is_authenticated and not request.user.is_staff:
        try:
            request.user.agent_profile
            return redirect('agents:overview')
        except AgentProfile.DoesNotExist:
            pass
    error = None
    success = None
    if request.method == 'POST':
        telegram_id = request.POST.get('telegram_id', '').strip()
        username = request.POST.get('username', '').strip()
        phone = request.POST.get('phone', '').strip()
        telegram_username = request.POST.get('telegram_username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if not telegram_id or not username or not phone or not password:
            error = 'All fields are required.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif User.objects.filter(username=username).exists():
            error = 'Username already taken. Choose another.'
        elif AgentRequest.objects.filter(telegram_id=int(telegram_id), status='pending').exists():
            error = 'You already have a pending agent request. Wait for admin approval.'
        elif AgentRequest.objects.filter(telegram_id=int(telegram_id), status='approved').exists():
            error = 'An agent account already exists for this Telegram ID.'
        else:
            try:
                tid = int(telegram_id)
                player = Player.objects.filter(telegram_id=tid).first()
            except (ValueError, TypeError):
                error = 'Invalid Telegram ID.'
            else:
                if player and AgentProfile.objects.filter(player=player, user__isnull=False).exists():
                    error = 'An agent account already exists for this Telegram ID.'
                elif not player:
                    Player.objects.create(
                        telegram_id=tid,
                        first_name=username,
                        phone_number=phone
                    )
                AgentRequest.objects.create(
                    telegram_id=tid,
                    username=username,
                    phone=phone,
                    telegram_username=telegram_username,
                    password_hash=hashers.make_password(password),
                )
                success = 'Registration submitted! Admin will review your request. You can login after approval.'

    return render(request, 'agents/register.html', {'error': error, 'success': success})


@agent_required
def overview(request):
    agent = request.agent_profile
    agent_player = request.agent_player
    referred = Player.objects.filter(invited_by=agent_player)
    total_deposited = sum(
        p.deposit_requests.filter(status='approved').aggregate(s=Sum('amount'))['s'] or 0
        for p in referred
    )
    active = referred.filter(games_played__gt=0).count()
    conversion = f'{int(active / max(referred.count(), 1) * 100)}%' if referred.count() else '0%'

    recent_entries = GameEntryLog.objects.filter(
        player__in=referred
    ).select_related('player').order_by('-created_at')[:20]

    return render(request, 'agents/overview.html', {
        'agent': agent,
        'agent_player': agent_player,
        'referred_count': referred.count(),
        'total_deposited': total_deposited,
        'active_players': active,
        'conversion': conversion,
        'recent_entries': recent_entries,
    })


@agent_required
def players_list(request):
    agent_player = request.agent_player
    referred = Player.objects.filter(invited_by=agent_player)
    player_data = []
    for p in referred:
        deposited = p.deposit_requests.filter(status='approved').aggregate(s=Sum('amount'))['s'] or 0
        earned = CommissionLedger.objects.filter(agent=agent_player, player=p).aggregate(
            s=Sum('commission_amount'))['s'] or 0
        player_data.append({
            'player': p,
            'total_deposited': deposited,
            'deposit_credit': p.deposit_credit,
            'games_played': p.games_played,
            'commission_earned': earned,
            'created_at': p.created_at,
        })
    return render(request, 'agents/players.html', {
        'agent_player': agent_player,
        'player_data': player_data,
    })


@agent_required
def commissions(request):
    agent_player = request.agent_player
    commission_list = CommissionLedger.objects.filter(
        agent=agent_player
    ).select_related('player', 'game_entry').order_by('-created_at')[:100]
    total = commission_list.aggregate(s=Sum('commission_amount'))['s'] or 0
    return render(request, 'agents/commissions.html', {
        'commissions': commission_list,
        'total_commission': total,
    })


@agent_required
def referral(request):
    agent_player = request.agent_player
    bot_username = 'Bingo2BingoBot'
    from django.conf import settings
    bot_username = getattr(settings, 'BOT_USERNAME', bot_username)
    link = f'https://t.me/{bot_username}?start={agent_player.referral_code}'
    referred = Player.objects.filter(invited_by=agent_player)
    return render(request, 'agents/referral.html', {
        'agent_player': agent_player,
        'referral_link': link,
        'referral_code': agent_player.referral_code,
        'referred_count': referred.count(),
    })
