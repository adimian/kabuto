#!/bin/bash
echo "Running build for kabuto"
docker build -t registry.adimian.com/kabuto/kabuto
docker push registry.adimian.com/kabuto/kabuto