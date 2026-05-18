from django.db import models
from django.utils import timezone
from users.models import Player


class Transaction(models.Model):
    class Type(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        GAME_ENTRY = 'game_entry', 'Game Entry Fee'
        GAME_WIN = 'game_win', 'Game Win'
        DRAW_REFUND = 'draw_refund', 'Draw Refund'
        HOUSE_FEE = 'house_fee', 'House Fee'
        DAILY_BONUS = 'daily_bonus', 'Daily Bonus'
        REFERRAL_BONUS = 'referral_bonus', 'Referral Bonus'
        SPIN_WIN = 'spin_win', 'Spin Win'
        ADMIN_GIFT = 'admin_gift', 'Admin Gift'

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='transactions')
    amount = models.BigIntegerField()
    transaction_type = models.CharField(max_length=20, choices=Type.choices)
    description = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} | {self.amount} coins | {self.player}"
