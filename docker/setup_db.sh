#!/bin/bash

if [ -e latest ]; then
	OLD=` date -r latest +%s 2>/dev/null `
else
	OLD=0
fi

wget -N https://r18.dev/dumps/latest
NEW=` date -r latest +%s 2>/dev/null `

if [ "$NEW" = "$OLD" ]; then
    echo "R18.dev Database Refresh Completed"
else
    psql -U postgres -c "DROP DATABASE IF EXISTS r18;"
	psql -U postgres -c "CREATE DATABASE r18;"
	zcat latest | psql -U postgres -d r18
	echo "R18.dev Database Refresh Completed"
fi



