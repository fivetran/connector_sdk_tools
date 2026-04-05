#!/bin/bash

#cd /home/ubuntu/connector_generator/backend/workspaces/

for user in *; do 
    if [ -d "$user/connectors" ]; then
        count=$(find "$user/connectors" -mindepth 1 -maxdepth 1 -type d | wc -l)
        echo "$user: $count"
    else
        echo "$user: 0"
    fi
done