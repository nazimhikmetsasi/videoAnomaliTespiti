# Kok requirements.txt goru yigini (torch, ultralytics, onnxruntime-gpu)
# tasir; API'nin hicbirine ihtiyaci yok. Ayri imaj, 2 GB'lik gereksiz katmandan
# ucuzdur (ASAMA5_PLAN.md SS10).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Baglam ./api oldugu icin paket /app/api altina duser -> api.main:app ve
# `python -m api.workers.consumer` calisir (SS10).
COPY . /app/api

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
