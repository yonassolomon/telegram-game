from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from django.conf import settings


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        target = query.edit_message_text
    else:
        target = update.message.reply_text

    webapp_url = getattr(settings, 'WEBAPP_URL', '')
    text = (
        f"🎮 *አጠቃቀም ህጎች / How to Play*\n\n"
        f"🏠 Room መፍጠር የማሸነፍ እድልዎን ይጨምራል!\n"
        f"👥 ከጓደኞችዎ ጋር Private Room ፈጥረው ይጫወቱ!\n"
        f"🔥 Arena Mode ትልቅ ሽልማት ያስገኛል!\n"
        f"💰 Deposit በ Staff Dashboard ይፀድቃል\n"
        f"🎁 ጓደኞችን ይጋብዙ +1/+5 Coin ያግኙ\n\n"
        f"📖 ሙሉ መመሪያ ለማግኘት Mini App ይክፈቱ👇"
    )
    kb = None
    if webapp_url and '127.0.0.1' not in webapp_url and 'localhost' not in webapp_url:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("📖 ሙሉ መመሪያ / Full Guide", web_app=WebAppInfo(url=webapp_url + 'help/'))
        ], [
            InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")
        ]])
    else:
        from bot.keyboards.inline import help_keyboard
        kb = help_keyboard()
    await target(text, reply_markup=kb, parse_mode='Markdown')
