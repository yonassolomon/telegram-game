from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from users.models import Player


class AgentProfile(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name='agent_profile')
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='agent_profile')
    agent_balance = models.BigIntegerField(default=0)
    total_commission_earned = models.BigIntegerField(default=0)
    total_deposit_volume = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Agent Profile'
        verbose_name_plural = 'Agent Profiles'

    def __str__(self):
        return f'Agent: {self.player.first_name} ({self.player.telegram_id})'


class AgentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    telegram_id = models.BigIntegerField(db_index=True)
    username = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    telegram_username = models.CharField(max_length=255, blank=True, default='')
    password_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='agent_requests_reviewed')
    created_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Agent Request'
        verbose_name_plural = 'Agent Requests'
        ordering = ['-created_at']

    def __str__(self):
        return f'Agent Request: {self.username} [{self.status}]'

    @property
    def referred_count(self):
        return self.player.invitees.count()

    @property
    def active_players_count(self):
        return self.player.invitees.filter(games_played__gt=0).count()


class GameEntryLog(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='game_entry_logs')
    entry_fee = models.BigIntegerField()
    used_deposit_credit = models.BigIntegerField(default=0)
    used_wallet_only = models.BigIntegerField(default=0)
    game_type = models.CharField(max_length=20, default='room')
    game_ref = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Game Entry Log'
        verbose_name_plural = 'Game Entry Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.player.first_name} | fee={self.entry_fee} | deposit_used={self.used_deposit_credit}'


class CommissionLedger(models.Model):
    agent = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='commission_earned')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='commission_generated')
    game_entry = models.OneToOneField(GameEntryLog, on_delete=models.CASCADE, related_name='commission')
    commission_amount = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Commission Ledger'
        verbose_name_plural = 'Commission Ledger'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.agent.first_name} ← {self.player.first_name} | {self.commission_amount} coins'
