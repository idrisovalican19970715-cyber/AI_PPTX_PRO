# AI_PPTX_PRO

Презентации из темы (Gemini) + фото по смыслу (Pexels / Unsplash / Wikimedia).

## У себя на компьютере

Дважды нажми **`ЗАПУСТИТЬ_У_СЕБЯ.bat`** или:

```bash
python -m pip install -r requirements.txt
python -m streamlit run main.py
```

Ключ Gemini — в `.env` (`GEMINI_API_KEY=...`) или в поле в приложении.

## В интернет для друзей (ПК может быть выключен)

Открой файл **`ЗАПУСК_В_ИНТЕРНЕТ.md`** — там всё по шагам: GitHub → Streamlit Cloud → Secrets.

Шаблон секретов для облака: **`secrets_for_streamlit_cloud.toml`**.

## Одна картинка из командной строки

```bash
python fetch_illustration.py "solar panels" -o pic.jpg
```
