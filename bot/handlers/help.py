from telegram import Update
from telegram.ext import ContextTypes
from bot.keyboards.inline import help_keyboard


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        target = query.edit_message_text
    else:
        target = update.message.reply_text

    text = (
        f"ℹ️ *How to Play Bingo2Bingo*\n\n"
        f"🎮 *Bingo Rules:*\n"
        f"1️⃣ Join or create a game room\n"
        f"2️⃣ Get your 5×5 bingo card\n"
        f"3️⃣ Numbers are called one by one\n"
        f"4️⃣ Mark 5 in a row, column, or diagonal to win!\n\n"
        f"🪙 *Coins:*\n"
        f"- Start with 500 coins\n"
        f"- Entry fee varies per room\n"
        f"- Winner takes the prize pool!\n"
        f"- Daily bonus: 100 coins\n\n"
        f"👥 *Referrals:*\n"
        f"- Invite friends, earn 100 coins each!\n\n"
        f"🏆 *Leaderboard:*\n"
        f"- Compete for top spots!\n\n"
        f"❓ *Need help?* Contact @admin"
    )
    await target(text, reply_markup=help_keyboard(), parse_mode='Markdown')
