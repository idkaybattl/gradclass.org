from django.urls import path

from . import views

urlpatterns = [
    path("", views.abi, name="abi"),
    path("calendar/", views.calendar, name="calendar"),
]
