# Пульт «Падачи» — установка на сервер

Сервис лежит рядом с лендингом и ассистентом, в `/opt/padacha/pult` — это
тот же клон репозитория `padacha-landing`, деплой не меняется: `git pull`
и перезапуск юнита (миграции и статика применяются сами при старте).

## Первая установка

```bash
cd /opt/padacha/pult
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
# в .env вписать DJANGO_SECRET_KEY:
python3 -c "import secrets; print(secrets.token_urlsafe(50))"

.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser

# база и статика должны принадлежать пользователю сервиса
chown -R www-data:www-data var staticfiles

sudo cp deploy/pult.service /etc/systemd/system/padacha-pult.service
sudo systemctl daemon-reload
sudo systemctl enable --now padacha-pult
```

Добавить в `/etc/nginx/sites-available/padacha` блоки из
[`nginx-snippet.conf`](nginx-snippet.conf) (перед последним `}` конфига):

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Проверить:

- https://padacha.ru/pult/ — форма входа админки;
- `curl -X POST https://padacha.ru/api/license/ -d '{"key":"x"}'` — 404
  «Ключ не найден» (эндпоинт жив, ключ чужой).

## Обновление

```bash
cd /opt/padacha && git pull
sudo systemctl restart padacha-pult
```

## Бэкап

Вся база — один файл `var/db.sqlite3`:

```bash
cp /opt/padacha/pult/var/db.sqlite3 ~/pult-backup-$(date +%F).sqlite3
```

## Подключение новой точки

1. В пульте создать клиента и точку — ключ лицензии сгенерируется сам.
2. Ключ положить в `.env` инстанса заведения (`LICENSE_KEY=...`,
   `LICENSE_URL=https://padacha.ru/api/license/`).
3. Инстанс раз в сутки запрашивает лицензию и сам показывает баннеры
   об оплате и блокирует разделы по лестнице статусов.
