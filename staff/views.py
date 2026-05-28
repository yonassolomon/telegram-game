import json
import logging
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone
from finance.models import DepositRequest, WithdrawalRequest
from users.models import Player
from wallets.models import Transaction

logger = logging.getLogger('bingo.staff')


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('staff:login')
        if not request.user.is_staff:
            return render(request, 'staff/login.html', {
                'error': 'Access denied. Staff only.'
            })
        return view_func(request, *args, **kwargs)
    return wrapper


def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('staff:deposits')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user and user.is_staff:
            auth_login(request, user)
            return redirect('staff:deposits')
        return render(request, 'staff/login.html', {'error': 'Invalid credentials or not staff.'})
    return render(request, 'staff/login.html')


def logout_view(request):
    auth_logout(request)
    return redirect('staff:login')


@staff_required
def deposits(request):
    deps = DepositRequest.objects.select_related('player', 'reviewed_by').order_by('-created_at')[:100]
    return render(request, 'staff/deposits.html', {'deposits': deps})


@staff_required
def withdrawals(request):
    wds = WithdrawalRequest.objects.select_related('player', 'reviewed_by').order_by('-created_at')[:100]
    return render(request, 'staff/withdrawals.html', {'withdrawals': wds})


# API Endpoints — reuse finance logic


@csrf_exempt
@require_POST
@staff_required
def api_approve_deposit(request, request_id):
    dep = get_object_or_404(DepositRequest, id=request_id)
    if dep.status != 'pending':
        return JsonResponse({'error': 'Already reviewed'})
    with db_transaction.atomic():
        dep.status = 'approved'
        dep.reviewed_by = request.user
        dep.reviewed_at = timezone.now()
        dep.save()
        Player.objects.filter(id=dep.player_id).update(coins=F('coins') + dep.amount)
        Transaction.objects.create(
            player=dep.player, amount=dep.amount,
            transaction_type='deposit',
            description=f'Deposit {dep.amount} approved by {request.user.username}')
        from referrals.models import Referral
        ref = Referral.objects.filter(invited=dep.player).first()
        if ref and not ref.reward_claimed:
            ref.inviter.coins = F('coins') + 5
            ref.inviter.save(update_fields=['coins'])
            Transaction.objects.create(
                player=ref.inviter, amount=5,
                transaction_type='referral_bonus',
                description=f'Deposit referral bonus from {dep.player.first_name}')
            ref.reward_claimed = True
            ref.save(update_fields=['reward_claimed'])
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@staff_required
def api_reject_deposit(request, request_id):
    dep = get_object_or_404(DepositRequest, id=request_id)
    if dep.status != 'pending':
        return JsonResponse({'error': 'Already reviewed'})
    dep.status = 'rejected'
    dep.reviewed_by = request.user
    dep.reviewed_at = timezone.now()
    dep.save()
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@staff_required
def api_approve_withdrawal(request, request_id):
    wd = get_object_or_404(WithdrawalRequest, id=request_id)
    if wd.status != 'pending':
        return JsonResponse({'error': 'Already reviewed'})
    with db_transaction.atomic():
        p = Player.objects.select_for_update().get(id=wd.player_id)
        if p.coins < wd.amount:
            return JsonResponse({'error': 'Insufficient coins'})
        p.coins = F('coins') - wd.amount
        p.save(update_fields=['coins'])
        wd.status = 'approved'
        wd.reviewed_by = request.user
        wd.reviewed_at = timezone.now()
        wd.save()
        Transaction.objects.create(
            player=p, amount=-wd.amount,
            transaction_type='withdrawal',
            description=f'Withdrawal {wd.amount} approved by {request.user.username}')
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@staff_required
def api_reject_withdrawal(request, request_id):
    wd = get_object_or_404(WithdrawalRequest, id=request_id)
    if wd.status != 'pending':
        return JsonResponse({'error': 'Already reviewed'})
    wd.status = 'rejected'
    wd.reviewed_by = request.user
    wd.reviewed_at = timezone.now()
    wd.save()
    return JsonResponse({'success': True})
