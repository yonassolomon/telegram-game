import time
import logging
from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger('bingo.arena')


class Command(BaseCommand):
    help = 'Run the Arena game engine (tick every 1 second)'

    def handle(self, *args, **options):
        from arena.engine import tick
        self.stdout.write(self.style.SUCCESS('🏟️ Arena Engine started (1s ticks)'))

        while True:
            try:
                tick()
            except Exception as e:
                logger.error(f'ARENA TICK ERROR: {e}')
            time.sleep(1)
