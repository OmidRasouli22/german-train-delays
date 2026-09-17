FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY collect.py parse.py stations.txt ./

# Write straight to the log instead of buffering, so docker logs shows
# what is happening now.
ENV PYTHONUNBUFFERED=1

CMD ["python", "collect.py"]
