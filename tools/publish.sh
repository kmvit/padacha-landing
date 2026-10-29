#!/usr/bin/env bash
# Выкатка сайта и выпуск статей по расписанию. Живёт на сервере, запускается
# cron'ом в 9:05 и 15:05 по Москве — и вручную вместо голого git pull:
#
#   ssh -J vpn -p 49197 root@a318f7177847.vps.myjino.ru /opt/padacha/tools/publish.sh
#
# Статьи пишутся заранее с временем публикации (content/blog/*.md,
# published: 2026-10-25 09:00). Генератор собирает только те, чьё время
# наступило; этот скрипт пересобирает блог и сообщает поисковикам о новых
# страницах через IndexNow.
#
# Собранные файлы (blog/, sitemap.xml) на сервере — производные от исходников
# и текущего времени, поэтому перед git pull они сбрасываются к коммиту и
# собираются заново: правок руками на сервере здесь нет и быть не должно.
set -euo pipefail

SITE=/opt/padacha
PY=/opt/padacha-build/bin/python   # отдельное окружение с markdown

# Тело в функции: git pull может обновить этот файл, а bash читает его
# по ходу выполнения — так скрипт целиком прочитан до первой команды.
main() {
    cd "$SITE"
    echo "== $(date '+%F %T')"

    before=$(ls -d blog/*/ | sort)

    git checkout -q -- blog sitemap.xml
    git clean -fdq -- blog
    git pull --ff-only -q
    "$PY" tools/article.py | grep -v '^собрано' || true

    after=$(ls -d blog/*/ | sort)
    fresh=$(comm -13 <(echo "$before") <(echo "$after") | sed 's#^#/#')

    if [ -n "$fresh" ]; then
        echo "вышли: $(echo $fresh)"
        "$PY" tools/indexnow.py $fresh /blog/
    else
        echo "новых статей нет"
    fi
}

main "$@"
