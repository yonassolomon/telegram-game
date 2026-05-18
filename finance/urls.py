from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('deposit/', views.deposit, name='deposit'),
    path('withdrawal/', views.withdrawal, name='withdrawal'),
]
