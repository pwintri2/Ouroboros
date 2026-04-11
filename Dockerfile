FROM python:3.11-slim
WORKDIR /app
# Copy only requirements first to leverage cache
COPY controller/requirements.txt /app/controller/requirements.txt
RUN pip install --no-cache-dir -r /app/controller/requirements.txt || true

# Copy project
COPY . /app

# Ensure `controller` package files can be imported as top-level modules
ENV PYTHONPATH=/app/controller:/app:$PYTHONPATH

CMD ["uvicorn", "controller.main:app", "--host", "0.0.0.0", "--port", "8000"]
