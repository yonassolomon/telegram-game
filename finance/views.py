import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction as db_transaction
from django.db.models import F, Count, Sum
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
            player_obj.refresh_from_db(fields=['wins', 'coins', 'first_deposit_at', 'wins_since_first_deposit'])
            from finance.models import WithdrawalRequest

            if not player_obj.first_deposit_at:
                error = ('⚠️ ገንዘብ ለማውጣት በመጀመሪያ ተቀማጭ ማድረግ አለብዎት።\n\n'
                         '🎁 የመጀመሪያ ተቀማጭዎ 2 እጥፍ (2×) ይሆናል!\n\n'
                         'ለምሳሌ፦\n'
                         '• 30 ብር ካስገቡ → 60 ኮይን ይቀበላሉ።\n'
                         '• 50 ብር ካስገቡ → 100 ኮይን ይቀበላሉ።\n'
                         '• 100 ብር ካስገቡ → 200 ኮይን ይቀበላሉ።\n\n'
                         'ይህ 2 እጥፍ (2×) ጉርሻ  ነው።')
            elif player_obj.wins_since_first_deposit < 1:
                error = '⚠️ ገንዘብ ካስገቡ በኋላ ቢያንስ አንድ ጨዋታ ማሸነፍ አለብዎት።'
            elif requested_amount < 15:
                error = '⚠️ የሚወጣው መጠን ቢያንስ 15 ብር መሆን አለበት።'
            elif requested_amount > player_obj.coins:
                error = '⚠️ የጠየቁት የማውጣት መጠን ካለዎት ቀሪ ሂሳብ በላይ ነው።'
            elif WithdrawalRequest.objects.filter(player=player_obj, status='pending').exists():
                error = 'You have a pending withdrawal. Please wait for it to be processed.\nአንድ በሂደት ላይ ያለ የማውጫ ጥያቄ አለዎት። እባክዎ መጀመሪያ ውጤቱን ይጠብቁ።'
            else:
                total_balance = player_obj.coins
                non_withdrawable = player_obj.balance_at_first_deposit
                max_withdrawable = total_balance - non_withdrawable
                if max_withdrawable <= 0:
                    error = '⚠️ ማውጣት የሚችሉት ገንዘብ የለም።'
                elif requested_amount > max_withdrawable:
                    actual_amount = max_withdrawable
                else:
                    actual_amount = requested_amount
            if not error and actual_amount > 0:
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
        'total_balance': total_balance if 'total_balance' in dir() else 0,
        'non_withdrawable': non_withdrawable if 'non_withdrawable' in dir() else 0,
        'needs_confirmation': (actual_amount > 0 and not success and not error),
        'remaining_balance': (total_balance - actual_amount) if 'total_balance' in dir() and 'actual_amount' in dir() and not error else 0,
    })


# ═══ Admin Dashboard ═══


@admin_required
def admin_deposits(request):
    from django.db.models import Sum
    deposits = DepositRequest.objects.filter(archived_date__isnull=True).select_related('player', 'reviewed_by').order_by('-created_at')[:100]
    total_approved = DepositRequest.objects.filter(status='approved', archived_date__isnull=True).aggregate(s=Sum('amount'))['s'] or 0
    return render(request, 'finance/admin_deposits.html', {
        'deposits': deposits,
        'total_approved': total_approved,
        'status_filter': request.GET.get('status', 'all'),
        'phonenumber': PHONENUMBER,
    })


@admin_required
def admin_withdrawals(request):
    from django.db.models import Sum
    withdrawals = WithdrawalRequest.objects.filter(archived_date__isnull=True).select_related('player', 'reviewed_by').order_by('-created_at')[:100]
    total_approved = WithdrawalRequest.objects.filter(status='approved', archived_date__isnull=True).aggregate(s=Sum('amount'))['s'] or 0
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

        player = Player.objects.select_for_update().get(id=dep.player_id)
        is_first = not player.first_deposit_at
        pre_deposit_balance = player.coins
        bonus_multiplier = 2 if is_first else 1
        total_coins = dep.amount * bonus_multiplier

        player.coins = F('coins') + total_coins
        player.deposit_credit = F('deposit_credit') + dep.amount
        if is_first:
            player.first_deposit_at = timezone.now()
            player.first_deposit_amount = dep.amount
            player.has_received_first_deposit_bonus = True
            player.balance_at_first_deposit = pre_deposit_balance
            player.save(update_fields=['coins', 'deposit_credit', 'first_deposit_at',
                                       'first_deposit_amount', 'has_received_first_deposit_bonus',
                                       'balance_at_first_deposit'])
        else:
            player.save(update_fields=['coins', 'deposit_credit'])

        Transaction.objects.create(
            player=dep.player, amount=total_coins,
            transaction_type='deposit',
            description=f'Deposit {dep.amount} approved by {request.user.username}' + (' (First Deposit 2x Bonus!)' if is_first else '')
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


@csrf_exempt
@require_POST
@admin_required
def api_archive_deposits(request):
    now = timezone.now()
    count = DepositRequest.objects.filter(archived_date__isnull=True).update(archived_date=now)
    logger.info(f'ADMIN: {request.user} archived {count} deposit requests')
    return JsonResponse({'success': True, 'count': count})


@csrf_exempt
@require_POST
@admin_required
def api_archive_withdrawals(request):
    now = timezone.now()
    count = WithdrawalRequest.objects.filter(archived_date__isnull=True).update(archived_date=now)
    logger.info(f'ADMIN: {request.user} archived {count} withdrawal requests')
    return JsonResponse({'success': True, 'count': count})


@admin_required
def deposit_history(request):
    from django.db.models.functions import TruncDate
    date_filter = request.GET.get('date', '')
    if date_filter:
        try:
            from datetime import datetime
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            archived = DepositRequest.objects.filter(
                archived_date__date=filter_date
            ).select_related('player', 'reviewed_by').order_by('-created_at')
            total = sum(a.amount for a in archived)
            return render(request, 'finance/deposit_history.html', {
                'archived': archived, 'date_filter': date_filter, 'single_date': True,
                'total': total,
            })
        except ValueError:
            pass

    dates = DepositRequest.objects.filter(archived_date__isnull=False).annotate(
        archive_day=TruncDate('archived_date')
    ).values('archive_day').annotate(count=Count('id'), total=Sum('amount')).order_by('-archive_day')

    return render(request, 'finance/deposit_history.html', {
        'dates': dates, 'date_filter': date_filter, 'single_date': False,
    })


@admin_required
def withdrawal_history(request):
    from django.db.models.functions import TruncDate
    date_filter = request.GET.get('date', '')
    if date_filter:
        try:
            from datetime import datetime
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            archived = WithdrawalRequest.objects.filter(
                archived_date__date=filter_date
            ).select_related('player', 'reviewed_by').order_by('-created_at')
            total = sum(w.amount for w in archived)
            return render(request, 'finance/withdrawal_history.html', {
                'archived': archived, 'date_filter': date_filter, 'single_date': True,
                'total': total,
            })
        except ValueError:
            pass

    dates = WithdrawalRequest.objects.filter(archived_date__isnull=False).annotate(
        archive_day=TruncDate('archived_date')
    ).values('archive_day').annotate(count=Count('id'), total=Sum('amount')).order_by('-archive_day')

    return render(request, 'finance/withdrawal_history.html', {
        'dates': dates, 'date_filter': date_filter, 'single_date': False,
    })
