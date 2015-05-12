#!/bin/bash
export PYTHONPATH=kabuto
find . -name "*.pyc" -delete && py.test --cov-config .coveragerc --cov-report html --cov kabuto
