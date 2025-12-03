#!/bin/bash
IP="10.102.251.1"
NAME=jonathan

scp -r . $NAME@"$IP":/home/"$NAME"/ladderboard
