export PYTHONPATH=kabuto
find . -name "*.pyc" -delete && py.test $@
