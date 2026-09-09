"""Тесты пульта — лестница статусов, продление платежом, подпись лицензии.

Ломаться молча тут может ровно три вещи: точка блокируется не тогда,
платёж не продлевает, подпись не сходится у инстанса. Их и проверяем.
"""
import hashlib
import hmac
import json
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Client, Instance, Payment, add_months


def make_instance(**kwargs) -> Instance:
    client = Client.objects.create(name="Кафе «Тест»")
    fields = dict(client=client, title="Точка", plan=Instance.Plan.START)
    fields.update(kwargs)
    return Instance.objects.create(**fields)


class StatusLadderTests(TestCase):
    def test_ladder(self):
        today = date(2026, 9, 9)
        inst = make_instance(paid_until=date(2026, 9, 30), grace_days=7)
        self.assertEqual(inst.status(today), Instance.Status.ACTIVE)
        # за 5 дней до конца — «заканчивается»
        self.assertEqual(inst.status(date(2026, 9, 26)), Instance.Status.EXPIRING)
        # день в день ещё не просрочка
        self.assertEqual(inst.status(date(2026, 9, 30)), Instance.Status.EXPIRING)
        # просрочено, но в грейсе — работает
        self.assertEqual(inst.status(date(2026, 10, 3)), Instance.Status.GRACE)
        self.assertEqual(inst.status(date(2026, 10, 7)), Instance.Status.GRACE)
        # грейс кончился
        self.assertEqual(inst.status(date(2026, 10, 8)), Instance.Status.BLOCKED)

    def test_internal_never_blocked(self):
        inst = make_instance(paid_until=date(2020, 1, 1), is_internal=True)
        self.assertEqual(inst.status(date(2026, 9, 9)), Instance.Status.ACTIVE)

    def test_trial_week_by_default(self):
        inst = make_instance()
        self.assertEqual(
            inst.paid_until, timezone.localdate() + timedelta(days=7)
        )


class PaymentTests(TestCase):
    def test_payment_extends_from_paid_until_when_prepaid(self):
        # ранняя оплата не сгорает: отсчёт от «оплачено до»
        future = timezone.localdate() + timedelta(days=10)
        inst = make_instance(paid_until=future)
        Payment.objects.create(instance=inst, amount=2990, months=1)
        inst.refresh_from_db()
        self.assertEqual(inst.paid_until, add_months(future, 1))

    def test_payment_extends_from_today_after_downtime(self):
        # после простоя пустые месяцы не оплачиваются задним числом
        inst = make_instance(paid_until=timezone.localdate() - timedelta(days=60))
        Payment.objects.create(instance=inst, amount=2990, months=2)
        inst.refresh_from_db()
        self.assertEqual(inst.paid_until, add_months(timezone.localdate(), 2))

    def test_editing_payment_does_not_extend_again(self):
        inst = make_instance()
        p = Payment.objects.create(instance=inst, amount=2990, months=1)
        inst.refresh_from_db()
        was = inst.paid_until
        p.comment = "поправили комментарий"
        p.save()
        inst.refresh_from_db()
        self.assertEqual(inst.paid_until, was)

    def test_add_months_clamps_short_month(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))


class LicenseEndpointTests(TestCase):
    def _post(self, body: dict):
        return self.client.post(
            "/api/license/", json.dumps(body), content_type="application/json"
        )

    def test_unknown_key_404(self):
        self.assertEqual(self._post({"key": "нет такого"}).status_code, 404)
        self.assertEqual(self._post({}).status_code, 404)

    def test_signed_response_and_telemetry(self):
        inst = make_instance(plan=Instance.Plan.MAX)
        res = self._post({"key": inst.license_key, "version": "3ab90f8"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        data = body["data"]
        self.assertEqual(data["plan"], "max")
        self.assertEqual(data["paid_until"], inst.paid_until.isoformat())

        # подпись сходится при той же канонизации, что будет у инстанса
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(
            inst.license_key.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(body["sign"], expected)

        # телеметрия записана
        inst.refresh_from_db()
        self.assertIsNotNone(inst.last_seen_at)
        self.assertEqual(inst.last_version, "3ab90f8")

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get("/api/license/").status_code, 405)
