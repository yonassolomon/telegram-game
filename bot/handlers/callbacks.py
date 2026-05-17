from telegram import Update
from telegram.ext import ContextTypes
from bot.handlers.start import start_command
from bot.handlers.menu import menu_callback
from bot.handlers.wallet import wallet_callback
from bot.handlers.leaderboard import leaderboard_callback
from bot.handlers.daily import daily_callback, claim_daily_callback
from bot.handlers.referral import referral_callback, copy_ref_callback
from bot.handlers.help import help_callback
from bot.handlers.play import (
    play_callback, create_room_callback, room_config_callback,
    confirm_create_room, join_room_callback, leave_room_callback
)
from bot.handlers.game import start_game_callback
from bot.handlers.join_room import join_private_info_callback


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    handlers = {
        'menu': menu_callback,
        'wallet': wallet_callback,
        'leaderboard': leaderboard_callback,
        'daily': daily_callback,
        'claim_daily': claim_daily_callback,
        'referral': referral_callback,
        'help': help_callback,
        'play': play_callback,
        'create_room': create_room_callback,
        'confirm_create': confirm_create_room,
        'join_private_info': join_private_info_callback,
    }

    if data in handlers:
        await handlers[data](update, context)
    elif data.startswith('roomfee_') or data.startswith('roomsize_'):
        await room_config_callback(update, context)
    elif data.startswith('join_'):
        await join_room_callback(update, context)
    elif data.startswith('leave_'):
        await leave_room_callback(update, context)
    elif data.startswith('start_'):
        await start_game_callback(update, context)
    elif data.startswith('lb_'):
        await leaderboard_callback(update, context)
    elif data.startswith('copyref_'):
        await copy_ref_callback(update, context)
    elif data == 'noop':
        await query.answer('Nothing to do here!')
    else:
        await query.answer('Unknown action')
