# Установка на сервер

Сервис лежит рядом с лендингом, в `/opt/padacha/assistant` — это тот же
клон репозитория `padacha-landing`, деплой не меняется: `git pull`.

## Первая установка

```bash
cd /opt/padacha/assistant
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # заполнить YC_FOLDER_ID, YC_API_KEY, RELOAD_TOKEN
python -m scripts.export_kb # первый снапшот, дальше собирается сам при старте юнита

sudo cp deploy/assistant.service /etc/systemd/system/padacha-assistant.service
sudo systemctl daemon-reload
sudo systemctl enable --now padacha-assistant
sudo systemctl status padacha-assistant
```

Добавить в `/etc/nginx/sites-available/padacha` блок из
[`nginx-snippet.conf`](nginx-snippet.conf) (перед последним `}` конфига) и
перезагрузить nginx:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Проверить:

```bash
curl -s https://padacha.ru/api/assistant/health
```

## Обновление после правки

Правка `index.html` (цены, FAQ) или `data/product/*.json` требует пересборки
снапшота — она уже стоит в `ExecStartPre`, поэтому достаточно:

```bash
cd /opt/padacha && git pull
sudo systemctl restart padacha-assistant
```

Не хочется рвать открытые диалоги перезапуском — можно перечитать снапшот
без рестарта:

```bash
cd /opt/padacha/assistant
.venv/bin/python -m scripts.export_kb
curl -X POST -H "X-Assistant-Token: $(grep RELOAD_TOKEN .env | cut -d= -f2)" \
  http://127.0.0.1:8100/api/reload
```

## Логи

```bash
journalctl -u padacha-assistant -f
```
