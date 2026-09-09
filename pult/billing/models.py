"""Клиенты, их точки и подписки.

Подписка не вынесена в отдельную модель намеренно: одна точка = одна
подписка, и лишний уровень вложенности только путал бы админку. Тариф
и оплачено-до живут прямо на точке (Instance).
"""
import calendar
import secrets
from datetime import date, timedelta

from django.db import models
from django.utils import timezone


def new_license_key() -> str:
    """Ключ лицензии — он же секрет подписи ответов для этой точки."""
    return secrets.token_hex(32)


def trial_end() -> date:
    """Новая точка получает бесплатную неделю — как обещает лэндинг."""
    return timezone.localdate() + timedelta(days=7)


def add_months(d: date, n: int) -> date:
    """d + n месяцев; 31-е укорачивается до конца короткого месяца."""
    m = d.month - 1 + n
    year = d.year + m // 12
    month = m % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class Client(models.Model):
    """Заказчик — кафе или сеть. Точки — в Instance."""

    name = models.CharField("Название", max_length=160)
    contact_person = models.CharField("Контактное лицо", max_length=160, blank=True)
    phone = models.CharField("Телефон", max_length=30, blank=True)
    email = models.EmailField("Email", blank=True)
    notes = models.TextField("Заметки", blank=True)
    created_at = models.DateTimeField("Появился", auto_now_add=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Instance(models.Model):
    """Точка клиента — один развёрнутый инстанс продукта на своём домене."""

    class Plan(models.TextChoices):
        # значения совпадают с SiteSettings.Plan в продукте — лицензия
        # отдаёт их инстансу как есть
        START = "start", "Старт"
        HALL = "hall", "Зал"
        MAX = "max", "Максимум"

    class Status(models.TextChoices):
        ACTIVE = "active", "Оплачено"
        EXPIRING = "expiring", "Заканчивается"
        GRACE = "grace", "Просрочено (грейс)"
        BLOCKED = "blocked", "Заблокировано"

    #: за сколько дней до конца оплаты показывать «заканчивается»
    EXPIRING_DAYS = 5

    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="instances",
        verbose_name="Клиент",
    )
    title = models.CharField(
        "Точка", max_length=160,
        help_text="Как различать точки клиента, напр. «Кафе на набережной»",
    )
    domain = models.CharField(
        "Домен", max_length=200, blank=True,
        help_text="Напр. moyokafe.padacha.ru",
    )
    license_key = models.CharField(
        "Ключ лицензии", max_length=64, unique=True, default=new_license_key,
        help_text="Кладётся в LICENSE_KEY в .env инстанса. Он же — секрет "
                  "подписи ответов лицензии.",
    )
    plan = models.CharField(
        "Тариф", max_length=8, choices=Plan.choices, default=Plan.START
    )
    paid_until = models.DateField(
        "Оплачено до", default=trial_end,
        help_text="Новая точка получает неделю бесплатно",
    )
    grace_days = models.PositiveSmallIntegerField(
        "Грейс, дней", default=7,
        help_text="Сколько дней после «оплачено до» точка ещё работает",
    )
    is_internal = models.BooleanField(
        "Своя точка", default=False,
        help_text="Наше заведение: не биллится и никогда не блокируется",
    )
    notes = models.TextField("Заметки", blank=True)
    created_at = models.DateTimeField("Подключена", auto_now_add=True)

    # Заполняются самим инстансом при суточном пинге лицензии — по ним
    # видно, живы ли все точки и кто отстал по версии.
    last_seen_at = models.DateTimeField("Выходила на связь", null=True, blank=True)
    last_version = models.CharField("Версия", max_length=40, blank=True)

    class Meta:
        verbose_name = "Точка"
        verbose_name_plural = "Точки"
        ordering = ["client__name", "title"]

    def __str__(self):
        return f"{self.client} — {self.title}"

    def status(self, today: date | None = None) -> str:
        """Лестница блокировки; сам запрет исполняет инстанс по этому полю."""
        if self.is_internal:
            return self.Status.ACTIVE
        if today is None:
            today = timezone.localdate()
        if today > self.paid_until + timedelta(days=self.grace_days):
            return self.Status.BLOCKED
        if today > self.paid_until:
            return self.Status.GRACE
        if today > self.paid_until - timedelta(days=self.EXPIRING_DAYS):
            return self.Status.EXPIRING
        return self.Status.ACTIVE


class Payment(models.Model):
    """Поступление денег за точку.

    Создание платежа само продлевает «оплачено до»: отметил оплату — точка
    продлилась, отдельного действия не нужно. Отсчёт — от большего из
    (сегодня, старое «оплачено до»): ранняя оплата не сгорает, а после
    простоя не оплачиваются задним числом пустые месяцы.
    """

    instance = models.ForeignKey(
        Instance, on_delete=models.CASCADE, related_name="payments",
        verbose_name="Точка",
    )
    amount = models.DecimalField("Сумма, ₽", max_digits=10, decimal_places=2)
    months = models.PositiveSmallIntegerField("Месяцев", default=1)
    paid_at = models.DateField("Дата оплаты", default=timezone.localdate)
    comment = models.CharField("Комментарий", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-paid_at", "-id"]

    def __str__(self):
        return f"{self.instance} — {self.amount} ₽ ({self.paid_at})"

    def save(self, *args, **kwargs):
        extend = self.pk is None  # продлеваем только при создании
        super().save(*args, **kwargs)
        if extend and self.months:
            inst = self.instance
            base = max(inst.paid_until, timezone.localdate())
            inst.paid_until = add_months(base, self.months)
            inst.save(update_fields=["paid_until"])
