import threading
import os


def post_fork(server, worker):
    if worker.age == 0:
        def _run_bot():
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
            import django
            django.setup()
            from bot.management.commands.runbot import Command
            Command().handle()

        def _run_arena():
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
            import django
            django.setup()
            from arena.management.commands.runarena import Command
            Command().handle()

        threading.Thread(target=_run_bot, daemon=True).start()
        threading.Thread(target=_run_arena, daemon=True).start()
