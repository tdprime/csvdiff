#!/usr/bin/env python3

import csv
import difflib
import io
import sys

class ResetStringIO(io.StringIO):
	def getvalue(self):
		try:
			return super().getvalue()
		finally:
			self.seek(0)
			self.truncate()

if __name__ == '__main__':
	with open(sys.argv[1]) as in1, open(sys.argv[2]) as in2:
		csv1 = csv.DictReader(in1)
		csv2 = csv.DictReader(in2)

		schema = set(csv1.fieldnames)
		schema = list(filter(lambda x: x in schema, csv2.fieldnames))
		# print('DEBUG: schema = [%s]' % (','.join(schema)))
		csvout = ResetStringIO()
		csvw = csv.DictWriter(csvout, fieldnames=schema, extrasaction='ignore')

		data1 = list()
		for row in csv1:
			csvw.writerow(row)
			row = csvout.getvalue()
			# sys.stdout.write('DEBUG: ' + row)
			data1.append(row)
		# print('DEBUG: %s has %d rows' % (sys.argv[1], len(data1)))

		data2 = list()
		for row in csv2:
			csvw.writerow(row)
			data2.append(csvout.getvalue())
		# print('DEBUG: %s has %d rows' % (sys.argv[2], len(data2)))

	print('Schema:')
	for x in difflib.ndiff(csv1.fieldnames, csv2.fieldnames):
		if x[0] != '?':
			print(x)
	print('\nRows:')
	for x in difflib.ndiff(data1, data2):
		if x[0] != ' ':
			print(x, end='')