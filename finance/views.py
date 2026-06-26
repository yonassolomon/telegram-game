import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone
from finance.models import DepositRequest, WithdrawalRequest
from users.models import Player
from wallets.models import Transaction
from dashboard.auth import admin_required
from webapp.views import get_player_from_request

logger = logging.getLogger('bingo.finance')

PHONENUMBER = '0922029734'


def deposit(request):
    player = get_player_from_request(request)
    if not player:
        return redirect('webapp:home')

    success = False
    error = None
    if request.method == 'POST':
        text = request.POST.get('telebirr_text', '').strip()
        try:
            amount = int(request.POST.get('amount', 0))
        except (ValueError, TypeError):
            amount = 0

        if not text:
            error = 'Please paste the Telebirr transaction text'
        elif len(text) < 5:
            error = 'Transaction text is too short'
        elif amount < 10:
            error = 'Minimum deposit amount is 10 coins'
        elif amount <= 0:
            error = 'Please enter a valid deposit amount'
        else:
            DepositRequest.objects.create(player=player, telebirr_text=text, amount=amount)
            success = True

    return render(request, 'finance/deposit.html', {
        'player': player,
        'phonenumber': PHONENUMBER,
        'success': success,
        'error': error,
    })


def withdrawal(request):
    player_obj = get_player_from_request(request)
    if not player_obj:
        return redirect('webapp:home')

    from users.models import Player
    NON_WITHDRAWABLE_BONUS = Player.NON_WITHDRAWABLE_BONUS
    MIN_WITHDRAWABLE_BALANCE = Player.MIN_WITHDRAWABLE_BALANCE

    success = False
    error = None
    actual_amount = 0
    requested_amount = 0
    if request.method == 'POST':
        try:
            requested_amount = int(request.POST.get('amount', 0))
        except (ValueError, TypeError):
            error = 'Invalid amount'
        else:
            if requested_amount < 10:
                error = 'Minimum withdrawal is 10 Birr'
            else:
                player_obj.refresh_from_db(fields=['wins', 'coins'])
                from finance.models import DepositRequest, WithdrawalRequest
                has_deposited = DepositRequest.objects.filter(player=player_obj, status='approved').exists()
                total_balance = player_obj.coins

                if total_balance < MIN_WITHDRAWABLE_BALANCE:
                    error = 'ገንዘብ ለማውጣት ቢያንስ 100 ብር በዋሌትዎ ውስጥ ሊኖር ይገባል።'
                elif player_obj.wins < 1 and not has_deposited:
                    error = 'You must win at least one game before withdrawing.\nእባክዎ ገንዘብ ከማውጣትዎ በፊት ቢያንስ አንድ ጨዋታ አሸንፈው መሆን አለበት።'
                elif WithdrawalRequest.objects.filter(player=player_obj, status='pending').exists():
                    error = 'You have a pending withdrawal. Please wait for it to be processed.\nአንድ በሂደት ላይ ያለ የማውጫ ጥያቄ አለዎት። እባክዎ መጀመሪያ ውጤቱን ይጠብቁ።'
                else:
                    max_withdrawable = total_balance - NON_WITHDRAWABLE_BONUS
                    actual_amount = max_withdrawable if requested_amount > max_withdrawable else requested_amount

                    if actual_amount <= 0:
                        error = 'የሚወጣ ገንዘብ የለም። 20 ብሩ የቦነስ ገንዘብ ስለሆነ ሊወጣ አይችልም።'
                    else:
                        receiving_number = request.POST.get('receiving_number', '')
                        player_obj.coins = F('coins') - actual_amount
                        player_obj.save(update_fields=['coins'])
                        WithdrawalRequest.objects.create(
                            player=player_obj, amount=actual_amount,
                            receiving_number=receiving_number
                        )
                        player_obj.refresh_from_db()
                        success = True

    return render(request, 'finance/withdrawal.html', {
        'player': player_obj,
        'success': success,
        'error': error,
        'actual_amount': actual_amount,
        'requested_amount': requested_amount,
    })


# ═══ Admin Dashboard ═══


@admin_required
def admin_deposits(request):
    from django.db.models import Sum
    deposits = DepositRequest.objects.select_related('player', 'reviewed_by').order_by('-created_at')[:100]
    total_approved = DepositRequest.objects.filter(status='approved').aggregate(s=Sum('amount'))['s'] or 0
    return render(request, 'finance/admin_deposits.html', {
        'deposits': deposits,
        'total_approved': total_approved,
        'status_filter': request.GET.get('status', 'all'),
        'phonenumber': PHONENUMBER,
    })


@admin_required
def admin_withdrawals(request):
    from django.db.models import Sum
    withdrawals = WithdrawalRequest.objects.select_related('player', 'reviewed_by').order_by('-created_at')[:100]
    total_approved = WithdrawalRequest.objects.filter(status='approved').aggregate(s=Sum('amount'))['s'] or 0
    return render(request, 'finance/admin_withdrawals.html', {
        'withdrawals': withdrawals,
        'total_approved': total_approved,
        'status_filter': request.GET.get('status', 'all'),
    })


@csrf_exempt
@require_POST
@admin_required
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
            description=f'Deposit {dep.amount} approved by {request.user.username}'
        )
        from referrals.models import Referral
        ref = Referral.objects.filter(invited=dep.player, reward_claimed=False).first()
        if ref:
            ref.inviter.coins = F('coins') + 3
            ref.inviter.save(update_fields=['coins'])
            Transaction.objects.create(
                player=ref.inviter, amount=3,
                transaction_type='referral_bonus',
                description=f'Deposit referral bonus from {dep.player.first_name}')
            ref.reward_claimed = True
            ref.save(update_fields=['reward_claimed'])

    logger.info(f'ADMIN: {request.user} approved deposit #{request_id} for player {dep.player.telegram_id}')
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@admin_required
def api_reject_deposit(request, request_id):
    dep = get_object_or_404(DepositRequest, id=request_id)
    if dep.status != 'pending':
        return JsonResponse({'error': 'Already reviewed'})

    dep.status = 'rejected'
    dep.reviewed_by = request.user
    dep.reviewed_at = timezone.now()
    dep.save()

    logger.info(f'ADMIN: {request.user} rejected deposit #{request_id}')
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@admin_required
def api_approve_withdrawal(request, request_id):
    wd = get_object_or_404(WithdrawalRequest, id=request_id)
    if wd.status != 'pending':
        return JsonResponse({'error': 'Already reviewed'})

    with db_transaction.atomic():
        wd.status = 'approved'
        wd.reviewed_by = request.user
        wd.reviewed_at = timezone.now()
        wd.save()
        Transaction.objects.create(
            player=wd.player, amount=-wd.amount,
            transaction_type='withdrawal',
            description=f'Withdrawal approved by {request.user.username}'
        )

    logger.info(f'ADMIN: {request.user} approved withdrawal #{request_id} for {wd.amount} coins')
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@admin_required
def api_reject_withdrawal(request, request_id):
    wd = get_object_or_404(WithdrawalRequest, id=request_id)
    if wd.status != 'pending':
        return JsonResponse({'error': 'Already reviewed'})

    with db_transaction.atomic():
        Player.objects.filter(id=wd.player_id).update(coins=F('coins') + wd.amount)
        wd.status = 'rejected'
        wd.reviewed_by = request.user
        wd.reviewed_at = timezone.now()
        wd.save()
        Transaction.objects.create(
            player=wd.player, amount=wd.amount,
            transaction_type='withdrawal_refund',
            description=f'Withdrawal #{request_id} rejected — refunded'
        )

    logger.info(f'ADMIN: {request.user} rejected withdrawal #{request_id} — refunded {wd.amount}')
    return JsonResponse({'success': True})
