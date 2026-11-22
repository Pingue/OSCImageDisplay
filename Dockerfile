FROM python:3.15-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# SDL loads the X11 client libraries at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libx11-6 libxext6 libxcursor1 libxi6 libxrandr2 libxfixes3 \
      libxss1 libxinerama1 libxxf86vm1 libxrender1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY oscimagedisplay.py .

RUN useradd --uid 1000 --create-home app && mkdir /images
USER app

VOLUME /images
EXPOSE 1340/udp
ENTRYPOINT ["python", "oscimagedisplay.py"]
CMD ["--directory", "/images"]
