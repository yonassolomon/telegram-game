from users.models import Player
from wallets.models import Transaction
from django.db import transaction as db_transaction


def get_or_create_player(telegram_id, username='', first_name=''):
    try:
        player = Player.objects.get(telegram_id=telegram_id)
        created = False
    except Player.DoesNotExist:
        player = Player.objects.create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name
        )
        created = True

    if not created and username:
        if player.username != username or player.first_name != first_name:
            player.username = username
            player.first_name = first_name
            player.save(update_fields=['username', 'first_name'])
    return player, created


def add_coins(player, amount, tx_type, description=''):
    with db_transaction.atomic():
        player.refresh_from_db()
        player.coins += amount
        player.save(update_fields=['coins'])
        Transaction.objects.create(
            player=player,
            amount=amount,
            transaction_type=tx_type,
            description=description
        )


def remove_coins(player, amount, tx_type, description=''):
    with db_transaction.atomic():
        player.refresh_from_db()
        if player.coins < amount:
            raise ValueError(f'Insufficient coins. Have {player.coins}, need {amount}')
        player.coins -= amount
        player.save(update_fields=['coins'])
        Transaction.objects.create(
            player=player,
            amount=-amount,
            transaction_type=tx_type,
            description=description
        )
