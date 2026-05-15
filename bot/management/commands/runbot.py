from django.core.management.base import BaseCommand
from django.conf import settings
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
import django
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run the Telegram Bingo Bot'

    def handle(self, *args, **options):
        django.setup()

        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            self.stderr.write('TELEGRAM_BOT_TOKEN not set in environment!')
            return

        from bot.handlers.start import start_command
        from bot.handlers.help import help_callback
        from bot.handlers.play import play_command
        from bot.handlers.callbacks import callback_router

        app = ApplicationBuilder().token(token).build()

        app.add_handler(CommandHandler('start', start_command))
        app.add_handler(CommandHandler('play', play_command))
        app.add_handler(CommandHandler('help', help_callback))
        app.add_handler(CallbackQueryHandler(callback_router))

        app.add_error_handler(self._error_handler)

        self.stdout.write(self.style.SUCCESS('🤖 Bingo2Bingo Bot is running...'))
        app.run_polling()

    async def _error_handler(self, update, context):
        logger.error(f'Update {update} caused error: {context.error}')
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    '⚠️ Something went wrong. Please try again.'
                )
            except Exception:
                pass
