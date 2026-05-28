#!/bin/bash
python manage.py runbot &
python manage.py runarena &
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --timeout 120
