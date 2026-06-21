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
    f"🎮 *አጠቃቀም መመሪያ*\n\n"
    f"• ለመጫወት የሚፈልጉትን ካርድ ብቻ ይምረጡ።\n\n"
    f"• በጨዋታ ካሸነፉ ተቀማጭ ገንዘብ (Deposit) ሳያስፈልግ ሽልማትዎን ማውጣት ይችላሉ።\n\n"
    f"• የገንዘብ ማውጫ (Withdrawal) ጥያቄዎች በአስተዳዳሪዎቻችን ተመርምረው ወደ መረጡት የመቀበያ ቁጥር ይላካሉ።\n\n"
    f"• ገንዘብ ሲያስገቡ የመቀበያ ቁጥሩን በትክክል መቅዳትና መለጠፍ (Copy/Paste) እንዳደረጉ ያረጋግጡ።\n\n"
    f"🎁 *ሽልማቶች እና ጉርሻዎች*\n\n"
    f"• 🎁 ጓደኞችን በመጋበዝ +1/+5 Coin ያግኙ።\n\n"
    f"• 🔥 በየቀኑ በመጫወት የተከታታይ ቀናት ሽልማቶችን ያግኙ።\n\n"
    f"• 🎉 የ3 ቀን ልዩ ዝግጅቶች፣ የሳምንት ልዩ ዝግጅቶች እና የወር ልዩ ዝግጅቶች በትልልቅ ሽልማቶች ይካሄዳሉ።\n\n"
    f"• 🏆 በልዩ ዝግጅቶች ላይ በመሳተፍ ትልልቅ ሽልማቶችን የማሸነፍ እድል ያገኛሉ።\n\n"
    f"📖 ሙሉ መመሪያ ለማግኘት Mini App ይክፈቱ 👇"
)
    kb = None
    if webapp_url and '127.0.0.1' not in webapp_url and 'localhost' not in webapp_url:
       kb = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu")
    ]
])
    else:
        from bot.keyboards.inline import help_keyboard
        kb = help_keyboard()
    await target(text, reply_markup=kb, parse_mode='Markdown')
