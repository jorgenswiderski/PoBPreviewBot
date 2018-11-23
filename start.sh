#!/bin/sh -x
cd /home/ec2-user/PoBPreviewBot

if ! screen -list | grep -q ".bot"; then
	#/usr/bin/screen -S bot -dmS /usr/local/bin/python /home/ec2-user/PoBPreviewBot/main.py
	screen -S bot -dmS python main.py
else
	#/usr/bin/screen -S bot -X /usr/local/bin/python /home/ec2-user/PoBPreviewBot/main.py
	screen -S bot -X python main.py
fi
