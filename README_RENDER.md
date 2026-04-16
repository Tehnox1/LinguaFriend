# Render deploy for LinguaFriend

## Что уже подготовлено

- `render.yaml` для веб-сервиса Render
- `gunicorn` в `requirements.txt`
- `SECRET_KEY` читается из переменных окружения

## Что важно знать

- `GitHub Pages` хостит только фронтенд из папки `docs/`
- `Render` запускает Flask API из `web_app.py`
- `leaderboard.json` на Render хранится во временной файловой системе

Это значит:
- после перезапуска сервиса локальный файл лидерборда может сброситься
- если нужен постоянный leaderboard, потом лучше вынести его в базу данных

## Куда нажимать на Render

1. Загрузите проект в GitHub
2. Откройте [https://render.com](https://render.com)
3. Нажмите `New +`
4. Выберите `Blueprint`
5. Подключите ваш GitHub-репозиторий
6. Выберите репозиторий с проектом
7. Render увидит файл `render.yaml`
8. Нажмите `Apply`
9. Дождитесь завершения деплоя

## Какой URL потом вставлять

После деплоя Render создаст адрес вида:

`https://linguafriend-api.onrender.com`

или похожий, если имя будет другим.

Именно этот адрес нужно вставить в:

`docs/config.js`

Пример:

```js
window.APP_CONFIG = {
  apiBaseUrl: "https://linguafriend-api.onrender.com"
};
```

Важно:

- вставляйте только базовый адрес
- не добавляйте `/api/state`
- не добавляйте `/api/answer`

## После этого

1. Закоммитьте обновленный `docs/config.js`
2. Загрузите изменения в GitHub
3. GitHub Pages подхватит новый фронтенд

## Если хотите проще

Можно вообще не использовать GitHub Pages, а выложить весь проект только на Render.
Тогда сайт и API будут работать с одного домена, и ничего не нужно будет прописывать в `config.js`.
