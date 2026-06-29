from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum
from django.contrib.auth.models import User
from django.utils import timezone
from agents.models import AgentProfile, GameEntryLog, CommissionLedger, AgentRequest
from users.models import Player
from dashboard.auth import admin_required


@admin_required
def agents_list(request):
    agents = AgentProfile.objects.select_related('player').annotate(
        total_players=Sum('player__invitees__id')
    ).order_by('-total_commission_earned')
    return render(request, 'agents/admin_agents.html', {'agents': agents})


@admin_required
def agent_detail(request, agent_id):
    agent = AgentProfile.objects.select_related('player').get(id=agent_id)
    referred = Player.objects.filter(invited_by=agent.player)
    commission_logs = CommissionLedger.objects.filter(agent=agent.player).select_related(
        'player', 'game_entry'
    ).order_by('-created_at')[:50]
    return render(request, 'agents/admin_agent_detail.html', {
        'agent': agent,
        'referred': referred,
        'commission_logs': commission_logs,
    })


@admin_required
def game_logs(request):
    logs = GameEntryLog.objects.select_related('player').order_by('-created_at')[:200]
    total_deposit_used = logs.aggregate(s=Sum('used_deposit_credit'))['s'] or 0
    total_wallet_used = logs.aggregate(s=Sum('used_wallet_only'))['s'] or 0
    return render(request, 'agents/admin_game_logs.html', {
        'logs': logs,
        'total_deposit_used': total_deposit_used,
        'total_wallet_used': total_wallet_used,
    })


@admin_required
def commission_ledger(request):
    commissions = CommissionLedger.objects.select_related(
        'agent', 'player', 'game_entry'
    ).order_by('-created_at')[:200]
    total = commissions.aggregate(s=Sum('commission_amount'))['s'] or 0
    return render(request, 'agents/admin_commission_ledger.html', {
        'commissions': commissions,
        'total_commission': total,
    })


@admin_required
def agent_requests(request):
    requests_list = AgentRequest.objects.order_by('-created_at')
    return render(request, 'agents/admin_agent_requests.html', {
        'requests_list': requests_list,
    })


@admin_required
def api_approve_agent(request, request_id):
    ar = get_object_or_404(AgentRequest, id=request_id)
    if ar.status != 'pending':
        from django.http import JsonResponse
        return JsonResponse({'error': 'Already reviewed'})

    base_username = ar.username
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f'{base_username}_{ar.telegram_id}'
        if User.objects.filter(username=username).exists():
            username = f'{base_username}_{ar.telegram_id}_{counter}'
            counter += 1

    user = User.objects.create_user(
        username=username,
        password='temp_placeholder',
        first_name=ar.username
    )
    user.password = ar.password_hash
    user.save()

    player, _ = Player.objects.get_or_create(
        telegram_id=ar.telegram_id,
        defaults={'first_name': ar.username, 'phone_number': ar.phone}
    )
    profile, created = AgentProfile.objects.get_or_create(player=player)
    if profile.user and profile.user != user:
        from django.http import JsonResponse
        return JsonResponse({'error': 'This Telegram ID already has an active agent account.'})
    profile.user = user
    profile.save(update_fields=['user'])

    ar.status = 'approved'
    ar.reviewed_by = request.user
    ar.reviewed_at = timezone.now()
    ar.save()

    from django.http import JsonResponse
    return JsonResponse({'success': True, 'username': username})


@admin_required
def api_reject_agent(request, request_id):
    ar = get_object_or_404(AgentRequest, id=request_id)
    if ar.status != 'pending':
        from django.http import JsonResponse
        return JsonResponse({'error': 'Already reviewed'})

    ar.status = 'rejected'
    ar.reviewed_by = request.user
    ar.reviewed_at = timezone.now()
    ar.save()

    from django.http import JsonResponse
    return JsonResponse({'success': True})
