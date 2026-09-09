"""Наружу торчат ровно два пути (их и проксирует nginx):

- /pult/         — админка, единственный UI пульта; вход только владельцу.
- /api/license/  — сюда раз в сутки стучатся инстансы заведений.

Корня «/» у сервиса нет — на домене padacha.ru его занимает лэндинг.
"""
from django.contrib import admin
from django.urls import path

from billing.views import license_view

urlpatterns = [
    path("pult/", admin.site.urls),
    path("api/license/", license_view, name="license"),
]
