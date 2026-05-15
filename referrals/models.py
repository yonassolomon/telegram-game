from django.db import models
from django.utils import timezone
from users.models import Player


class Referral(models.Model):
    inviter = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name='referrals_made'
    )
    invited = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name='referral_received'
    )
    reward_claimed = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Referral'
        verbose_name_plural = 'Referrals'
        unique_together = ('inviter', 'invited')

    def __str__(self):
        return f"{self.inviter} → {self.invited}"
