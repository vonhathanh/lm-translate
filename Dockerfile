FROM python:3.11

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./server /code/server

COPY ./.env /code/.env

CMD ["fastapi", "run", "server/main.py", "--port", "5000"]