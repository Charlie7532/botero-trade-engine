#!/bin/bash
ping -c 1 -W 3 google.com > /dev/null 2>&1 && echo "Internet OK" || echo "Internet error"
