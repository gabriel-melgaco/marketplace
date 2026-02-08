FROM python:3.12-slim

WORKDIR /api

COPY . .

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install --no-deps drf-auth-kit==1.1.1

EXPOSE 5000

CMD python manage.py migrate && python manage.py runserver 0.0.0.0:5000
