from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('player', 'amount', 'transaction_type', 'description', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('player__username', 'player__telegram_id', 'description')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
