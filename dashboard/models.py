from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class AdminLog(models.Model):
    class Action(models.TextChoices):
        COIN_ADD = 'coin_add', 'Coins Added'
        COIN_DEDUCT = 'coin_deduct', 'Coins Deducted'
        COIN_RESET = 'coin_reset', 'Coins Reset'
        PLAYER_BAN = 'player_ban', 'Player Banned'
        PLAYER_UNBAN = 'player_unban', 'Player Unbanned'
        ROOM_CLOSE = 'room_close', 'Room Force Closed'
        PLAYER_KICK = 'player_kick', 'Player Kicked'
        GAME_END = 'game_end', 'Game Ended'

    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    target_player = models.ForeignKey('users.Player', on_delete=models.SET_NULL, null=True, blank=True)
    target_room = models.ForeignKey('games.GameRoom', on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.BigIntegerField(null=True, blank=True)
    detail = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Admin Log'
        verbose_name_plural = 'Admin Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.created_at:%H:%M}] {self.admin_user} → {self.get_action_display()}'


class DailyReset(models.Model):
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    day_number = models.IntegerField(default=1)
    deposit_total = models.BigIntegerField(default=0)
    withdrawal_total = models.BigIntegerField(default=0)
    house_fee_total = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Daily Reset'
        verbose_name_plural = 'Daily Resets'
        ordering = ['-created_at']

    def __str__(self):
        return f'Day {self.day_number} — D:{self.deposit_total} W:{self.withdrawal_total} H:{self.house_fee_total}'
