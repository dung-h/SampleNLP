FROM python:3.12-slim
WORKDIR /app
COPY experiments/slide_pipeline/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY experiments/slide_pipeline /app/experiments/slide_pipeline
COPY data/raw /app/data/raw
COPY data/annotations /app/data/annotations
ENV PYTHONPATH=/app
ENTRYPOINT ["python", "-m", "experiments.slide_pipeline"]
CMD ["--demo"]
