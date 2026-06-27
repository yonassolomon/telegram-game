from django.db import transaction as db_transaction
from django.db.models import F, Sum
from django.contrib.auth.models import User
from users.models import Player
from agents.models import AgentProfile, GameEntryLog, CommissionLedger
import random
import string

COMMISSION_RATE = 0.05


def _random_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def get_or_create_agent(player):
    agent_player = player.invited_by
    if not agent_player:
        return None
    profile, _ = AgentProfile.objects.get_or_create(player=agent_player)
    return profile


def ensure_agent_user(agent_player):
    profile = AgentProfile.objects.filter(player=agent_player).first()
    if not profile:
        return None
    if profile.user:
        return profile
    username = f'agent_{agent_player.telegram_id}'
    user, created = User.objects.get_or_create(
        username=username,
        defaults={'first_name': agent_player.first_name, 'is_active': True}
    )
    if created:
        password = _random_password()
        user.set_password(password)
        user.save()
    profile.user = user
    profile.save(update_fields=['user'])
    return profile


def promote_to_agent_on_deposit(deposited_player):
    agent_player = deposited_player.invited_by
    if not agent_player:
        return
    profile = get_or_create_agent(deposited_player)
    ensure_agent_user(agent_player)


def process_game_entry(player, entry_fee, game_type='arena', game_ref=''):
    with db_transaction.atomic():
        p = Player.objects.select_for_update().get(id=player.id)
        if p.coins < entry_fee:
            raise ValueError('Insufficient coins')

        deposit_credit_used = min(p.deposit_credit, entry_fee)
        wallet_only_used = entry_fee - deposit_credit_used

        p.coins = F('coins') - entry_fee
        p.deposit_credit = F('deposit_credit') - deposit_credit_used
        p.save(update_fields=['coins', 'deposit_credit'])

        log = GameEntryLog.objects.create(
            player=p,
            entry_fee=entry_fee,
            used_deposit_credit=deposit_credit_used,
            used_wallet_only=wallet_only_used,
            game_type=game_type,
            game_ref=game_ref,
        )
        return log


def calculate_and_award_commission(game_entry_log):
    if game_entry_log.used_deposit_credit <= 0:
        return None

    if CommissionLedger.objects.filter(game_entry=game_entry_log).exists():
        return None

    player = game_entry_log.player
    agent_player = player.invited_by
    if not agent_player:
        return None

    commission = int(game_entry_log.used_deposit_credit * COMMISSION_RATE)
    if commission <= 0:
        return None

    total_deposited = player.deposit_requests.filter(status='approved').aggregate(
        s=Sum('amount'))['s'] or 0
    max_commission = int(total_deposited * COMMISSION_RATE)

    total_earned = CommissionLedger.objects.filter(
        agent=agent_player, player=player
    ).aggregate(s=Sum('commission_amount'))['s'] or 0

    if total_earned + commission > max_commission:
        commission = max_commission - total_earned
        if commission <= 0:
            return None

    with db_transaction.atomic():
        profile = AgentProfile.objects.select_for_update().get(player=agent_player)
        profile.agent_balance = F('agent_balance') + commission
        profile.total_commission_earned = F('total_commission_earned') + commission
        profile.save(update_fields=['agent_balance', 'total_commission_earned'])

        ledger = CommissionLedger.objects.create(
            agent=agent_player,
            player=player,
            game_entry=game_entry_log,
            commission_amount=commission,
        )
        return ledger


def process_entry_and_commission(player, entry_fee, game_type='arena', game_ref=''):
    log = process_game_entry(player, entry_fee, game_type, game_ref)
    if log.used_deposit_credit > 0:
        calculate_and_award_commission(log)
    return log
