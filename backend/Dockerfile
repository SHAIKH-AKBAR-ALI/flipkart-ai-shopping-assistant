FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

COPY . .

ENV PORT=7860
EXPOSE 7860

CMD ["uvicorn", "app_v2:app", "--host", "0.0.0.0", "--port", "7860"]
