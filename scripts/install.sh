#!/bin/bash

if [ -d "/config/custom_components/thingsboard" ]; then
    echo "Removing existing integration"
    rm -rf /config/custom_components/thingsboard
fi

if [ ! -d "/config/custom_components" ]; then
    echo "Creating custom_components directory"
    mkdir -p /config/custom_components
fi

if [ -d "/tmp/ha_thingsboard-main" ]; then
    echo "Removing existing files"
    rm -rf /tmp/ha_thingsboard-main
fi

if [ -f "/tmp/ha_thingsboard-main.zip" ]; then
    echo "Removing existing zip file"
    rm /tmp/ha_thingsboard-main.zip
fi

wget -O /tmp/ha_thingsboard-main.zip "https://github.com/connected-intelligent-systems/ha_thingsboard/archive/refs/heads/main.zip" && \
    unzip /tmp/ha_thingsboard-main.zip -d /tmp/ && \
    mv /tmp/ha_thingsboard-main/custom_components/thingsboard /config/custom_components/ && \
    rm -rf /tmp/ha_thingsboard-main && \
    rm /tmp/ha_thingsboard-main.zip