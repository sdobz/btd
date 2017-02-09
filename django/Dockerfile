FROM python:2.7

ENV PYTHONUNBUFFERED 1
RUN mkdir -p /opt/python/
WORKDIR /opt/python/
ADD requirements.pip /opt/python/
RUN pip install -r requirements.pip
