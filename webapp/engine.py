import random
import threading
import time
from django.utils import timezone
from django.db import models as db_models


def run_game_engine(room_code):
    from games.models import GameRoom, BingoCard, GameHistory
    from users.models import Player
    from wallets.models import Transaction

    room = GameRoom.objects.get(room_code=room_code)
    cards = list(BingoCard.objects.filter(game_room=room).select_related('player'))

    numbers = list(range(1, 76))
    random.shuffle(numbers)
    called = []
    winner_card = None

    for number in numbers:
        if winner_card:
            break

        called.append(number)

        for card in cards:
            card.mark_number(number)
            card.save(update_fields=['marked'])

            if card.check_win():
                winner_card = card
                break

        history, _ = GameHistory.objects.get_or_create(
            game_room=room,
            defaults={'numbers_called': [], 'prize_distributed': 0}
        )
        history.numbers_called = called
        history.save(update_fields=['numbers_called'])

        time.sleep(2)

    room.refresh_from_db()
    room.status = 'finished'
    room.finished_at = timezone.now()

    if winner_card:
        winner = winner_card.player
        prize = room.prize_pool
        winner.coins = db_models.F('coins') + prize
        winner.wins = db_models.F('wins') + 1
        winner.xp = db_models.F('xp') + 100
        winner.games_played = db_models.F('games_played') + 1
        winner.save(update_fields=['coins', 'wins', 'xp', 'games_played'])
        room.winner = winner

        Transaction.objects.create(
            player=winner, amount=prize,
            transaction_type='game_win',
            description=f'Won room {room_code}'
        )

    room.save()

    for card in cards:
        if card != winner_card:
            p = card.player
            p.losses = db_models.F('losses') + 1
            p.games_played = db_models.F('games_played') + 1
            p.xp = db_models.F('xp') + 25
            p.save(update_fields=['losses', 'games_played', 'xp'])

    gh = GameHistory.objects.filter(game_room=room).first()
    if gh:
        gh.prize_distributed = room.prize_pool if winner_card else 0
        gh.winner = room.winner
        gh.save(update_fields=['prize_distributed', 'winner'])


def start_game_thread(room_code):
    thread = threading.Thread(target=run_game_engine, args=(room_code,), daemon=True)
    thread.start()
