from django.db import models
from django.utils import timezone
from users.models import Player
from django.contrib.auth.models import User


class DepositRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.BigIntegerField(default=0)
    telebirr_text = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Deposit Request'
        verbose_name_plural = 'Deposit Requests'
        ordering = ['-created_at']

    def __str__(self):
        return f'Deposit #{self.id} — {self.player} [{self.status}]'


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Withdrawal Request'
        verbose_name_plural = 'Withdrawal Requests'
        ordering = ['-created_at']

    def __str__(self):
        return f'Withdrawal #{self.id} — {self.player} [{self.status}]'
