# Variables
#$IP = "10.102.251.4"
$IP = "raspi04.kinet.ch"
$NAME = "ilann"
$Source = ".\*"
$RemotePath = "/home/$NAME/ladderboard"

# Build the target string
#$Target = "$NAME@$IP`:$RemotePath"
$Target = "$NAME@$IP`:$RemotePath"

scp -r $Source "$Target"
