#!/bin/bash

# Check R18.dev for latest dump
wget -N https://r18.dev/dumps/latest
# Remove existing database
echo "DROP DATABASE IF EXISTS r18;" | docker exec -i postgres psql -U postgres
# Load dump to new database
echo "CREATE DATABASE r18;" | docker exec -i postgres psql -U postgres
zcat latest | docker exec -i postgres psql -U postgres -d r18
