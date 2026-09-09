"""Админка — весь UI пульта.

Пользователь один (владелец «Падачи»), поэтому кастомный интерфейс не
пишем: список точек со статусами, карточка клиента с точками, платёж
в два клика — всё это админка умеет из коробки.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Client, Instance, Payment

admin.site.site_header = "Пульт «Падачи»"
admin.site.site_title = "Пульт «Падачи»"
admin.site.index_title = "Клиенты, точки, подписки"

STATUS_COLORS = {
    Instance.Status.ACTIVE: "#1a7f37",
    Instance.Status.EXPIRING: "#b58900",
    Instance.Status.GRACE: "#d1242f",
    Instance.Status.BLOCKED: "#6e0b14",
}


class InstanceInline(admin.TabularInline):
    model = Instance
    extra = 0
    fields = ("title", "domain", "plan", "paid_until", "is_internal")
    show_change_link = True


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "points")
    search_fields = ("name", "contact_person", "phone", "email")
    inlines = [InstanceInline]

    @admin.display(description="Точек")
    def points(self, obj):
        return obj.instances.count()


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("amount", "months", "paid_at", "comment")


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "client",
        "domain",
        "plan",
        "paid_until",
        "status_badge",
        "last_seen_at",
        "last_version",
    )
    list_filter = ("plan", "is_internal")
    search_fields = ("title", "domain", "client__name")
    inlines = [PaymentInline]
    readonly_fields = ("license_key", "last_seen_at", "last_version", "created_at")
    fieldsets = (
        (None, {"fields": ("client", "title", "domain", "notes")}),
        (
            "Подписка",
            {
                "fields": ("plan", "paid_until", "grace_days", "is_internal"),
                "description": "Оплату удобнее отмечать платежом внизу — "
                "«оплачено до» продлится само.",
            },
        ),
        (
            "Лицензия",
            {
                "fields": ("license_key", "last_seen_at", "last_version", "created_at"),
                "description": "Ключ кладётся в LICENSE_KEY в .env инстанса "
                "при подключении.",
            },
        ),
    )

    @admin.display(description="Статус")
    def status_badge(self, obj):
        status = obj.status()
        return format_html(
            '<b style="color:{}">{}</b>',
            STATUS_COLORS.get(status, "#000"),
            dict(Instance.Status.choices).get(status, status),
        )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("paid_at", "instance", "amount", "months", "comment")
    list_filter = ("paid_at",)
    date_hierarchy = "paid_at"
