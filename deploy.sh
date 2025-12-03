#!/bin/bash
IP="10.102.251.1"
NAME=jonathan

scp -r /home/jonathan/dev/infoplus $NAME@"$IP":/home/"$NAME"/ladderboard
