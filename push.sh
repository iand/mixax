#!/bin/sh

git add . && git commit -a && git pull && git push -u heroku master
