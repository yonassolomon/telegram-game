from django.contrib import admin
from .models import Referral


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('inviter', 'invited', 'reward_claimed', 'created_at')
    list_filter = ('reward_claimed', 'created_at')
    search_fields = ('inviter__username', 'invited__username')
    readonly_fields = ('created_at',)
