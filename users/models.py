from django.db import models
from django.utils import timezone
import uuid


class Player(models.Model):
    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, blank=True, default='')
    first_name = models.CharField(max_length=255, blank=True, default='')
    phone_number = models.CharField(max_length=20, blank=True, default='')
    coins = models.BigIntegerField(default=20)
    locked_balance = models.BigIntegerField(default=0)
    deposit_credit = models.BigIntegerField(default=0)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    games_played = models.IntegerField(default=0)
    xp = models.BigIntegerField(default=0)
    level = models.IntegerField(default=1)
    referral_code = models.CharField(max_length=32, unique=True, blank=True)
    registration_bonus_claimed = models.BooleanField(default=False)
    streak_count = models.IntegerField(default=0)
    last_streak_date = models.DateField(null=True, blank=True)
    streak_reward_claimed = models.IntegerField(default=0)
    invited_by = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='invitees'
    )
    is_banned = models.BooleanField(default=False)
    registration_bonus_claimed = models.BooleanField(default=False)
    last_daily_bonus = models.DateTimeField(null=True, blank=True)
    first_deposit_at = models.DateTimeField(null=True, blank=True)
    first_deposit_amount = models.BigIntegerField(default=0)
    has_received_first_deposit_bonus = models.BooleanField(default=False)
    wins_since_first_deposit = models.IntegerField(default=0)
    balance_at_first_deposit = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Player'
        verbose_name_plural = 'Players'
        ordering = ['-coins']

    def __str__(self):
        return f"{self.username or self.first_name} ({self.telegram_id})"

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = uuid.uuid4().hex[:10]
        super().save(*args, **kwargs)

    def can_claim_daily(self):
        if not self.last_daily_bonus:
            return True
        elapsed = timezone.now() - self.last_daily_bonus
        return elapsed.total_seconds() >= 86400

    def add_coins(self, amount):
        self.coins = models.F('coins') + amount
        self.save(update_fields=['coins'])

    def remove_coins(self, amount):
        if self.coins < amount:
            raise ValueError('Insufficient coins')
        self.coins = models.F('coins') - amount
        self.save(update_fields=['coins'])
