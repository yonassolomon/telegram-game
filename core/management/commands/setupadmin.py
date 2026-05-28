from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Create default admin user if not exists'

    def handle(self, *args, **options):
        if not User.objects.filter(username='admintelegrambingo').exists():
            User.objects.create_superuser('admintelegrambingo', '', 'yona3027!@#')
            self.stdout.write('Superuser created: admintelegrambingo')
        else:
            self.stdout.write('Superuser already exists')
