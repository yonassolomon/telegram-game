from django.db import models
from django.utils import timezone
from users.models import Player


class GameRound(models.Model):
    class Status(models.TextChoices):
        WAITING = 'waiting', 'Card Selection'
        ACTIVE = 'active', 'Game Running'
        FINISHED = 'finished', 'Completed'
        COOLDOWN = 'cooldown', 'Between Rounds'

    class CallMode(models.TextChoices):
        AUTO = 'auto', 'Auto'
        MANUAL = 'manual', 'Manual'

    round_number = models.IntegerField(default=1)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    call_mode = models.CharField(max_length=10, choices=CallMode.choices, default=CallMode.AUTO)
    entry_fee = models.BigIntegerField(default=10)
    prize_pool = models.BigIntegerField(default=0)
    platform_fee_percent = models.IntegerField(default=7)
    winner = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name='arena_wins')
    winners_data = models.JSONField(null=True, blank=True)
    numbers_called = models.JSONField(default=list)
    winner_card_number = models.IntegerField(null=True, blank=True)
    waiting_started_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    game_state = models.JSONField(default=dict, blank=True)
    bot_count = models.IntegerField(default=2)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Game Round'
        verbose_name_plural = 'Game Rounds'
        ordering = ['-created_at']

    def __str__(self):
        return f'Round #{self.round_number} [{self.status}]'

    @property
    def player_count(self):
        return self.selections.count()

    @property
    def waiting_seconds_left(self):
        if self.status != self.Status.WAITING or not self.waiting_started_at:
            return 0
        elapsed = (timezone.now() - self.waiting_started_at).total_seconds()
        return max(0, 30 - int(elapsed))


class CardSelection(models.Model):
    MAX_CARDS_PER_PLAYER = 3

    round = models.ForeignKey(GameRound, on_delete=models.CASCADE, related_name='selections')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='arena_selections')
    card_number = models.IntegerField()
    chosen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Card Selection'
        verbose_name_plural = 'Card Selections'
        constraints = [
            models.UniqueConstraint(fields=['round', 'card_number'], name='unique_card_per_round'),
        ]

    def __str__(self):
        return f'Round #{self.round.round_number} — {self.player.first_name} → Card #{self.card_number}'


class RoundQueue(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='arena_queue')
    preferred_card = models.IntegerField(null=True, blank=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Round Queue'
        verbose_name_plural = 'Round Queue'
        ordering = ['joined_at']

    def __str__(self):
        return f'Queue: {self.player.first_name}'
