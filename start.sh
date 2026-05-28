#!/bin/bash
python manage.py setupadmin
python manage.py runbot &
python manage.py runarena &
sleep 2
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --timeout 120 -c gunicorn_conf.py
