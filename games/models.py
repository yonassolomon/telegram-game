import json
from django.db import models
from django.utils import timezone
from users.models import Player


class GameRoom(models.Model):
    class RoomType(models.TextChoices):
        PUBLIC = 'public', 'Public'
        PRIVATE = 'private', 'Private'

    class Status(models.TextChoices):
        WAITING = 'waiting', 'Waiting'
        ACTIVE = 'active', 'Active'
        FINISHED = 'finished', 'Finished'

    class GameMode(models.TextChoices):
        AUTO = 'auto', 'Auto'
        MANUAL = 'manual', 'Manual'

    room_code = models.CharField(max_length=8, unique=True, blank=True)
    room_type = models.CharField(max_length=10, choices=RoomType.choices, default=RoomType.PUBLIC)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    max_players = models.IntegerField(default=10)
    entry_fee = models.BigIntegerField(default=50)
    prize_pool = models.BigIntegerField(default=0)
    winner = models.ForeignKey(
        Player, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='games_won'
    )
    players = models.ManyToManyField(Player, through='BingoCard', related_name='game_rooms')
    game_mode = models.CharField(max_length=10, choices=GameMode.choices, default=GameMode.AUTO)
    game_state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Game Room'
        verbose_name_plural = 'Game Rooms'
        ordering = ['-created_at']

    def __str__(self):
        return f"Room {self.room_code} [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.room_code:
            import uuid
            self.room_code = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)

    @property
    def player_count(self):
        return self.bingo_cards.count()

    @property
    def can_start(self):
        return self.status == self.Status.WAITING and self.player_count >= 2


class BingoCard(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='bingo_cards')
    game_room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='bingo_cards')
    numbers = models.JSONField(default=list)
    marked = models.JSONField(default=list)
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Bingo Card'
        verbose_name_plural = 'Bingo Cards'
        unique_together = ('player', 'game_room')

    def __str__(self):
        return f"Card #{self.id} | {self.player} | Room {self.game_room.room_code}"

    def mark_number(self, number):
        if number in self.numbers and number not in self.marked:
            self.marked.append(number)
            self.marked.sort()
            return True
        return False

    def check_win(self):
        size = 5
        grid = []
        for i in range(size):
            row = []
            for j in range(size):
                row.append(1 if self.numbers[i * size + j] in self.marked else 0)
            grid.append(row)

        for i in range(size):
            if sum(grid[i]) == size:
                return True
            col_sum = sum(grid[j][i] for j in range(size))
            if col_sum == size:
                return True

        diag1 = sum(grid[i][i] for i in range(size))
        diag2 = sum(grid[i][size - 1 - i] for i in range(size))
        if diag1 == size or diag2 == size:
            return True

        return False


class GameHistory(models.Model):
    game_room = models.OneToOneField(GameRoom, on_delete=models.CASCADE, related_name='history')
    players = models.ManyToManyField(Player, related_name='game_histories')
    winner = models.ForeignKey(
        Player, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='win_histories'
    )
    numbers_called = models.JSONField(default=list)
    prize_distributed = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Game History'
        verbose_name_plural = 'Game Histories'
        ordering = ['-created_at']

    def __str__(self):
        return f"Game #{self.game_room.room_code}"
