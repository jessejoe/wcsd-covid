# wscd-covid
Script for getting Covid data from the WCSD daily updates, and publishing them to pre-existing Flourish charts

Can use `Dockerfile` to build an image to run the script e.g.:
```
docker run --rm -v ./wcsd-covid/:/code --env 'FLOURISH_USERNAME=foo@bar.com' --env 'FLOURISH_PASSWORD=password' wcsd-covid bash -c "python /code/get-wcsd-covid-results.py"
```
