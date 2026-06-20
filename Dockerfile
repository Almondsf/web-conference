FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# dummy values only for collectstatic during build — real values come from Render's environment at runtime
ENV SECRET_KEY=build-time-placeholder
ENV DATABASE_URL=sqlite:///build.db
ENV REDIS_URL=redis://localhost:6379

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD python manage.py migrate && daphne -b 0.0.0.0 -p $PORT config.asgi:application