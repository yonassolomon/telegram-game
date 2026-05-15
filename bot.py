from telegram.ext import ApplicationBuilder, CommandHandler

TOKEN = "8518267393:AAGPStO57xkQ0IlWRXbt4pJqpO-U8keri8I"

async def start(update, context):
    await update.message.reply_text(
        "🎉 Welcome to Bingo Bot!"
    )

async def play(update, context):
    import random

    number = random.randint(1, 5)

    if number == 3:
        await update.message.reply_text("🏆 You won!")
    else:
        await update.message.reply_text("❌ Try again!")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("play", play))

app.run_polling()