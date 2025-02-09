# R18dev SQL Scraper

# Database Setup

This scraper requires access to a PostgreSQL server with R18.dev data. 

A docker compose file and a bash script to fetch and import the latest R18.dev database dump can be found under `docker/`. Simply run `docker compose up --build -d` and then `docker exec -it postgres /setup_db.sh` to set up a PostgreSQL database with R18.dev data. To update your database to the latest snapshot, rerun `docker exec -it postgres /setup_db.sh` after restarting the docker image.

If you already have PostgreSQL installed, you can find the latest R18.dev database dump [here](https://r18.dev/dumps).

# Initial setup

1. Run `pip install psycopg2-binary` to install the psycopg2 library.
2. Adjust the PostgreSQL connection string in `R18dev_SQL.py` if you are using your own PostgreSQL setup
3. ????
