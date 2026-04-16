# LinguaFriend on GitHub Pages

## Что уже подготовлено

- Готовая папка `docs/` для GitHub Pages
- Статический `index.html`
- Ассеты в `docs/static/`
- Файл `docs/config.js` для адреса API

## Важно

GitHub Pages умеет хостить только статические файлы.
Файл `web_app.py` и Python-бэкенд на GitHub Pages не запускаются.

Поэтому схема такая:

1. Фронтенд публикуется через GitHub Pages из папки `docs/`
2. Бэкенд Flask публикуется отдельно:
   - Render
   - Railway
   - Replit
   - VPS

## Как включить GitHub Pages

1. Загрузите проект в GitHub
2. Откройте `Settings -> Pages`
3. В `Build and deployment` выберите:
   - `Source`: `Deploy from a branch`
   - `Branch`: `main`
   - `Folder`: `/docs`

## Как подключить API

Откройте файл `docs/config.js` и укажите адрес вашего Flask API:

```js
window.APP_CONFIG = {
  apiBaseUrl: "https://your-backend.onrender.com"
};
```

Без этого GitHub Pages откроет интерфейс, но не сможет получать задания и ответы от бэкенда.

## Локальная структура

- `docs/` — версия для GitHub Pages
- `templates/` + `static/` — версия для Flask
- `web_app.py` — Flask API

## Совет

Если хотите, следующим шагом можно полностью упростить проект и сделать одну общую структуру:

- `frontend/` для сайта
- `backend/` для Flask
- отдельный конфиг для деплоя

Такой вариант удобнее для GitHub, Render и дальнейшей поддержки.
