FROM python
RUN mkdir /code
WORKDIR /code
COPY requirements.txt /code
RUN pip install -r /code/requirements.txt
