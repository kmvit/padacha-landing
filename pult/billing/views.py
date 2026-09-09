"""Эндпоинт лицензии — единственный API пульта.

Инстанс заведения раз в сутки присылает свой ключ и получает тариф,
«оплачено до» и статус. Ответ подписан HMAC-SHA256 с ключом лицензии:
инстанс проверяет подпись и не верит ничему неподписанному — иначе
блокировка обходилась бы подменой ответа или локальным прокси.

Подписывается канонический JSON блока data: ключи отсортированы,
разделители без пробелов. Инстанс сериализует так же и сверяет.
"""
import hashlib
import hmac
import json

from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Instance


def _canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


@csrf_exempt
def license_view(request: HttpRequest):
    """POST /api/license/  {"key": "...", "version": "..."}"""
    if request.method != "POST":
        return JsonResponse({"detail": "Только POST"}, status=405)
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Некорректный JSON"}, status=400)

    key = str(payload.get("key", ""))
    instance = Instance.objects.filter(license_key=key).first() if key else None
    if instance is None:
        # Не различаем «нет ключа» и «ключ не найден» — нечего подсказывать.
        return JsonResponse({"detail": "Ключ не найден"}, status=404)

    instance.last_seen_at = timezone.now()
    instance.last_version = str(payload.get("version", ""))[:40]
    instance.save(update_fields=["last_seen_at", "last_version"])

    data = {
        "plan": instance.plan,
        "paid_until": instance.paid_until.isoformat(),
        "grace_days": instance.grace_days,
        "status": instance.status(),
        # По issued_at инстанс отличает свежий ответ от сохранённого
        # старого: кэшу старше нескольких дней доверять нельзя.
        "issued_at": timezone.now().isoformat(),
    }
    sign = hmac.new(key.encode(), _canonical(data), hashlib.sha256).hexdigest()
    return JsonResponse({"data": data, "sign": sign})
