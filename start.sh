#!/bin/bash
python manage.py runbot > /tmp/bot.log 2>&1 &
python manage.py runarena > /tmp/arena.log 2>&1 &
sleep 2
echo "=== BOT LOG ===" && cat /tmp/bot.log
echo "=== ARENA LOG ===" && cat /tmp/arena.log
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --timeout 120
