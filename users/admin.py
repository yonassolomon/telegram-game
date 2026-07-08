from django.contrib import admin
from .models import Player


@admin.register(Player) 
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'username', 'first_name', 'coins', 'wins', 'losses', 'level', 'is_banned', 'created_at')
    list_filter = ('is_banned', 'level', 'created_at')
    search_fields = ('telegram_id', 'username', 'first_name')
    readonly_fields = ('telegram_id', 'referral_code', 'created_at')
    ordering = ('-coins',)
    actions = ['ban_users', 'unban_users', 'add_500_coins']

    def ban_users(self, request, queryset):
        queryset.update(is_banned=True)
    ban_users.short_description = 'Ban selected users'

    def unban_users(self, request, queryset):
        queryset.update(is_banned=False)
    unban_users.short_description = 'Unban selected users'

    def add_500_coins(self, request, queryset):
        from django.db.models import F
        queryset.update(coins=F('coins') + 500)
    add_500_coins.short_description = 'Add 500 coins to selected users'
