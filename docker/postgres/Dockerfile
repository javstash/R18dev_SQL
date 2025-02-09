FROM postgres:17.2-bookworm

RUN apt update
RUN apt install -y wget --no-install-recommends
RUN apt install --reinstall ca-certificates

EXPOSE 5432
CMD docker-entrypoint.sh postgres