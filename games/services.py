from .models import BingoCard
from core.utils import generate_bingo_card


def create_bingo_card(player, game_room):
    numbers = generate_bingo_card()
    card = BingoCard.objects.create(
        player=player,
        game_room=game_room,
        numbers=numbers,
        marked=[]
    )
    return card
