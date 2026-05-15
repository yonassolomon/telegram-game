from django.contrib import admin
from .models import GameRoom, BingoCard, GameHistory


@admin.register(GameRoom)
class GameRoomAdmin(admin.ModelAdmin):
    list_display = ('room_code', 'room_type', 'status', 'entry_fee', 'prize_pool', 'winner', 'player_count', 'created_at')
    list_filter = ('status', 'room_type', 'created_at')
    search_fields = ('room_code',)
    readonly_fields = ('room_code', 'created_at', 'started_at', 'finished_at')
    ordering = ('-created_at',)


@admin.register(BingoCard)
class BingoCardAdmin(admin.ModelAdmin):
    list_display = ('id', 'player', 'game_room', 'is_winner', 'created_at')
    list_filter = ('is_winner',)
    search_fields = ('player__username', 'game_room__room_code')


@admin.register(GameHistory)
class GameHistoryAdmin(admin.ModelAdmin):
    list_display = ('game_room', 'winner', 'prize_distributed', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('game_room__room_code', 'winner__username')
    readonly_fields = ('created_at',)
