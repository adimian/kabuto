print "making big file"
with open('/outbox/big_file.txt', 'wb') as fh:
    fh.write(str(range(10 ** 6)))
print "done making big file"
