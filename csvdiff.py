#!/usr/bin/env python3
# Copyright 2021 Timothy D. Prime

import csv
import difflib
import operator
import signal
import sys
import time

# https://pypi.org/project/termcolor/
import termcolor

FMT_EQUAL  = lambda x: x
TOK_EQUAL  = ' '
FMT_DELETE = lambda x: termcolor.colored(x, 'red')
TOK_DELETE = FMT_DELETE('-')
FMT_INSERT = lambda x: termcolor.colored(x, 'green')
TOK_INSERT = FMT_INSERT('+')

# TODO: see difflib.context_diff
def csvdiff(a, b):
	csvout = csv.writer(sys.stdout)
	cruncher = difflib.SequenceMatcher(None, a, b)
	for tag, alo, ahi, blo, bhi in cruncher.get_opcodes():
		# Order by expected cardinality. Most frequent first.
		if tag == 'equal':
			pass
		elif tag == 'replace':
			#sys.stdout.write('@@ -%d-%d +%d-%d @@\n' % (alo, ahi, blo, bhi))
			csvreplace(a, b, alo, ahi, blo, bhi)
		elif tag == 'insert':
			for row in b[blo:bhi]:
				sys.stdout.write(TOK_INSERT)
				csvout.writerow(list(map(FMT_INSERT, row)))
		elif tag == 'delete':
			for row in a[alo:ahi]:
				sys.stdout.write(TOK_DELETE)
				csvout.writerow(list(map(FMT_DELETE, row)))

# Super simple. Best for ranges with the same length.
def simple_replace(a, b, alo, ahi, blo, bhi):
	csvout = csv.writer(sys.stdout)
	alen = ahi - alo
	blen = bhi - blo
	i, j = alo, blo
	while alen > blen:
		sys.stdout.write(TOK_DELETE)
		csvout.writerow(list(map(FMT_DELETE, a[i])))
		i += 1
		alen -= 1

	while alen > 0:
		rowa = list()
		rowb = list()
		for x,y in zip(a[i], b[j]):
			if x == y:
				rowa.append(x)
				rowb.append(y)
			else:
				rowa.append(FMT_DELETE(x))
				rowb.append(FMT_INSERT(y))
		sys.stdout.write(TOK_DELETE)
		csvout.writerow(rowa)
		sys.stdout.write(TOK_INSERT)
		csvout.writerow(rowb)
		i += 1
		j += 1
		alen -= 1
		blen -= 1

	while blen > 0:
		sys.stdout.write(TOK_INSERT)
		csvout.writerow(list(map(FMT_INSERT, b[j])))
		j += 1
		blen -= 1

# count matching columns per pair of rows
#
# Turn on cache for "ndiff" style. Yes, it's big.
#@functools.lru_cache(maxsize=1<<20)
def rowcompare(a, b):
	return sum(map(operator.eq, a, b))

# Inspired by ndiff. Take advantage of the data's structure to better inform
# how they compare.
#
# Using rowcompare() is ~2x the speed of SequenceMatcher.ratio()
def fancy_replace(a, b, alo, ahi, blo, bhi):
	# cutoff is 66%
	best = (len(a[0]) * .66, None, None)
	for j in range(blo, bhi):
		for i in range(alo, ahi):
			score = rowcompare(a[i], b[j])
			if best[0] < score:
				best = (score, i, j)
	if best[1] is None:
		simple_replace(a, b, alo, ahi, blo, bhi)
		return
	fancy_replace(a, b, alo, best[1], blo, best[2])
	simple_replace(a, b, best[1], best[1]+1, best[2], best[2]+1)
	fancy_replace(a, b, best[1]+1, ahi, best[2]+1, bhi)

# Search for the best total score for arranging a[alo:ahi] and b[blo:bhi].
# Imagine using a recursive algorithm, each step is one of three actions: print
# a[alo] (delete), b[blo] (insert), or both as a replacement.  Replacements are
# scored by rowcompare(). Other actions are zero.

def csvreplace(a, b, alo, ahi, blo, bhi):
	# Build a table of scores on the tuple (i, ahi, j, bhi), later abbreviated
	# as (i, j). As i->alo and j->blo, values derived from previous
	# calculations. Finally arriving at the score for (alo, ahi, blo, bhi).
	best = dict()
	isrep = dict()
	for j in reversed(range(blo, bhi)):
		for i in reversed(range(alo, ahi)):
			do_delete = best.get((i+1, j), 0)
			do_insert = best.get((i, j+1), 0)
			do_both = best.get((i+1, j+1), 0)
			do_both += rowcompare(a[i], b[j])
			if do_both >= do_delete:
				if do_both >= do_insert:
					best[i, j] = do_both
					isrep[i, j] = True
				else:
					best[i, j] = do_insert
			else:
				if do_delete > do_insert:
					best[i, j] = do_delete
				else:
					best[i, j] = do_insert

	# Walk a path through the table to print the results.
	i, j = alo, blo
	while i < ahi and j < bhi:
		#print("DEBUG: i=%d, j=%d" % (i, j))
		if isrep.get((i, j)):
			simple_replace(a, b, i, i+1, j, j+1)
			i += 1
			j += 1
		else:
			do_delete = best.get((i+1, j), 0)
			do_insert = best.get((i, j+1), 0)
			if do_delete > do_insert:
				simple_replace(a, b, i, i+1, j, j)
				i += 1
			else:
				simple_replace(a, b, i, i, j, j+1)
				j += 1
	simple_replace(a, b, i, ahi, j, bhi)

# used to diff schema
def diffprint(line, **kwargs):
	if line[0] == ' ':
		print(line, **kwargs)
	elif line[0] == '+':
		termcolor.cprint(line, 'green', **kwargs)
	elif line[0] == '-':
		termcolor.cprint(line, 'red', **kwargs)
	elif line[0] == '?':
		print(line, **kwargs)
	elif line[0] == '@':
		termcolor.cprint(line, attrs=['bold'], **kwargs)
	else:
		termcolor.cprint(line, attrs=['reverse'], **kwargs)

if __name__ == '__main__':
	signal.signal(signal.SIGPIPE, signal.SIG_DFL)

	with open(sys.argv[1]) as in1, open(sys.argv[2]) as in2:
		csv1 = csv.DictReader(in1)
		csv2 = csv.DictReader(in2)

		# schema is the set union of the two CSV field names.
		# Keep the order of the "new" CSV.
		schema = set(csv1.fieldnames)
		schema = tuple(filter(lambda x: x in schema, csv2.fieldnames))
		#print('DEBUG: schema = [%s]' % (','.join(schema)))
		# Using tuple as a hashable (immutable) Row type.
		hrow = operator.itemgetter(*schema)
		data1 = list(map(hrow, csv1))
		data2 = list(map(hrow, csv2))

	print('Schema:')
	for x in difflib.ndiff(csv1.fieldnames, csv2.fieldnames):
		if x[0] != '?':
			diffprint(x)
	print('\nRows:')
	t_start = time.time()
	csvdiff(data1, data2)
	#print('time %0.1fms' % (1000.*(time.time() - t_start)), file=sys.stderr)
	#print(rowcompare.cache_info(), file=sys.stderr)
