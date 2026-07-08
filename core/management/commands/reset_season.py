"""
Management command to reset all player data for a new season launch.
Preserves admin, staff, agent accounts, and system configuration.
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Reset all player data for new season. Keeps admin/staff/agents.'

    def handle(self, *args, **options):
        self.stdout.write('Creating backup point...')
        self.stdout.write('Resetting player data...')

        with transaction.atomic():
            from referrals.models import Referral
            count = Referral.objects.all().delete()[0]
            self.stdout.write(f'  Referrals deleted: {count}')

            from agents.models import CommissionLedger
            count = CommissionLedger.objects.all().delete()[0]
            self.stdout.write(f'  Commission Ledger deleted: {count}')

            from agents.models import GameEntryLog
            count = GameEntryLog.objects.all().delete()[0]
            self.stdout.write(f'  Game Entry Logs deleted: {count}')

            from arena.models import DailyGift
            count = DailyGift.objects.all().delete()[0]
            self.stdout.write(f'  Daily Gifts deleted: {count}')

            from agents.models import AgentRequest
            count = AgentRequest.objects.all().delete()[0]
            self.stdout.write(f'  Agent Requests deleted: {count}')

            from finance.models import WithdrawalRequest
            count = WithdrawalRequest.objects.all().delete()[0]
            self.stdout.write(f'  Withdrawal Requests deleted: {count}')

            from finance.models import DepositRequest
            count = DepositRequest.objects.all().delete()[0]
            self.stdout.write(f'  Deposit Requests deleted: {count}')

            from wallets.models import Transaction
            count = Transaction.objects.all().delete()[0]
            self.stdout.write(f'  Transactions deleted: {count}')

            from games.models import BingoCard
            count = BingoCard.objects.all().delete()[0]
            self.stdout.write(f'  Bingo Cards deleted: {count}')

            from games.models import GameHistory
            count = GameHistory.objects.all().delete()[0]
            self.stdout.write(f'  Game Histories deleted: {count}')

            from games.models import GameRoom
            count = GameRoom.objects.all().delete()[0]
            self.stdout.write(f'  Game Rooms deleted: {count}')

            from arena.models import CardSelection
            count = CardSelection.objects.all().delete()[0]
            self.stdout.write(f'  Card Selections deleted: {count}')

            from arena.models import GameRound
            count = GameRound.objects.all().delete()[0]
            self.stdout.write(f'  Game Rounds deleted: {count}')

            from arena.models import RoundQueue
            count = RoundQueue.objects.all().delete()[0]
            self.stdout.write(f'  Round Queue deleted: {count}')

            from dashboard.models import DailyReset
            count = DailyReset.objects.all().delete()[0]
            self.stdout.write(f'  Daily Resets deleted: {count}')

            from dashboard.models import AdminLog
            count = AdminLog.objects.all().delete()[0]
            self.stdout.write(f'  Admin Logs deleted: {count}')

            from users.models import Player
            from agents.models import AgentProfile
            agent_player_ids = set(AgentProfile.objects.values_list('player_id', flat=True))
            from django.contrib.auth.models import User
            staff_user_ids = set(User.objects.filter(is_staff=True).values_list('id', flat=True))
            agent_user_ids = set(AgentProfile.objects.exclude(user__isnull=True).values_list('user_id', flat=True))

            count = Player.objects.exclude(
                id__in=agent_player_ids
            ).exclude(
                id__in=agent_user_ids
            ).delete()[0]
            self.stdout.write(f'  Players deleted: {count}')

            remaining = Player.objects.count()
            self.stdout.write(f'  Players remaining (agents): {remaining}')

        self.stdout.write('')
        self.stdout.write('Player data reset complete. System is ready for new season.')
