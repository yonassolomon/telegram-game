from django.urls import path
from . import dashboard_views as views

app_name = 'agents'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.overview, name='overview'),
    path('players/', views.players_list, name='players'),
    path('commissions/', views.commissions, name='commissions'),
    path('referral/', views.referral, name='referral'),
]
