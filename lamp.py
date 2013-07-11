#!/usr/bin/env python

# Run multiple testing correction.
# This script need transaction file, expression-file and significance-level.
# transaction-file: The file includes associations between TFs and genes.
#     Each line indicates a gene.
#     If gene is targeted by the TF, then value is 1, otherwise 0.
# expression-file: Each line indicates a gene. The column1 is gene name.
#     If gene has the feature, the column2 is 1. The other case 0.
# significance-level: The statistical significance threshold.
# @author Terada 26, June, 2011

import sys, os.path, time
import transaction
import readFile as readFile
import frepattern.frequentPatterns as frequentPatterns
from optparse import OptionParser

import functions.functionsSuper as fs
import functions.functions4fisher as functions4fisher
import functions.functions4u_test as functions4u_test
import functions.functions4chi as functions4chi

set_opts = ("fisher", "u_test", "chi") # methods which used each test

class MASLError(Exception):
	def __init__(self, e):
		sys.stderr.write("MASLError: " + e + "\n")
	

##
# Return the bound of given minimum support.
##
def calBound( func_f, min_sup, fre_pattern ):
	# If lower bound is not calculated, calculate the value and save to fre_pattern.
	if fre_pattern.getBound( min_sup ) > 1:
		bound = func_f.funcF( min_sup ) # minimum support value
		fre_pattern.setBound( min_sup, bound ) # save
	return fre_pattern.getBound( min_sup ) 
	
##
# Run multiple test.
# transaction_list: List of itemset and expression value.
# trans4lcm: File name for argument of LCM program. This file is made in this method.
# threshold: The statistical significance threshold.
# columnid2name: Mapping between TS id to TF name.
# lcm2transaction_id: Mapping between LCM ID to transaction id.
# set_method: The procedure name for calibration p-value (fisher/u_test).
##
def executeMultTest(transaction_list, trans4lcm, threshold, set_method, lcm_pass, max_comb):
	max_lambda = maxLambda(transaction_list)
	lam_star = 1; func_f = None;
	try:
		if set_method == "fisher":
			func_f = functions4fisher.FunctionOfX(transaction_list, max_lambda)
		elif set_method == "u_test":
			func_f = functions4u_test.FunctionOfX(transaction_list)
		elif set_method == "chi":
			print set_method
			func_f = functions4chi.FunctionOfX(transaction_list, max_lambda)
		else:
			sys.stderr.write("Error: choose \"fisher\", \"chi\" or \"u_test\".\n")
			sys.exit
				
	except fs.TestMethodError, e:
		sys.exit()
	try:
		lam = max_lambda
		
		# check a MASL of max_lambda
		if (set_method == 'fisher') or (set_method == 'chi'):
			n1 = func_f.sumValue(transaction_list)
			if (n1 < max_lambda):
				max_lambda = int( n1 )
				lam = int( n1 )
				
		fre_pattern = frequentPatterns.LCM(lcm_pass, max_lambda)
		fre_pattern.makeFile4Lem(transaction_list, trans4lcm) # make itemset file for lcm
		# If file for Lcm exist, comfiem that overwrite the file.
		# solve K and lambda
		while lam > 1:
			sys.stderr.write("--- lambda: " + str(lam) + " ---\n")
			# if lambda == 1, all tests which support >= 1 are tested.
			if lam == 1:
				lam_star = lam
				fre_pattern.frequentPatterns( trans4lcm, lam, max_comb ) # line 3 of Algorithm
				k = fre_pattern.getTotal( lam )
				break

			fre_pattern.frequentPatterns( trans4lcm, lam, max_comb ) # line 3 of Algorithm
			m_lambda = fre_pattern.getTotal( lam ) # line 4 of Algorithm
			sys.stderr.write("  m_lambda: " + str(m_lambda) + "\n")
			
			f_lam_1 = calBound( func_f, lam-1, fre_pattern ) # f(lam-1)
			sys.stderr.write("  f(" + str(lam-1) + ") = " + str(f_lam_1) + "\n")
#			sys.stderr.write(str(threshold) + "//" + str(f_lam_1) + "\n")
			if (f_lam_1 == 0):
				bottom = sys.maxint
			else:
				bottom = (threshold//f_lam_1) + 1 # bottom of line 5 of Algorithm
			f_lam = calBound( func_f, lam, fre_pattern ) # f(lam)
			sys.stderr.write("  f(" + str(lam) + ") = " + str(f_lam) + "\n")
			# If f(lambda) > f(lambda-1), raise error.
			# Because MASL f(x) is smaller if x is larger.
			if f_lam > f_lam_1:
				e_out = "f(" + str(lam) + ") is larger than f(" + str(lam-1) + ")"
				sys.stderr.write("MASLError: " + e_out + "\n")
				sys.exit()
			if (f_lam == 0):
				top = sys.maxint
			else:
				top = threshold//f_lam # top of line 5 of Algorithm
			sys.stderr.write("  " + str(bottom) + " <= m_lam:" + str(m_lambda) + " <= " + str(top) + "?\n")
			if bottom <= m_lambda and m_lambda <= top: # branch on condition of line 5
				k = m_lambda
				lam_star = lam
				break
			sys.stderr.write("  " + str(m_lambda) + " > " + str(top) + "?\n")
			if m_lambda > top: # branch on condition of line 8
				lam_star = lam
				break
			lam = lam -1
	except fs.TestMethodError, e:
		sys.exit()
	except frequentPatterns.LCMError, e:
		sys.exit()
	
	try:
		fre_pattern.frequentPatterns( trans4lcm, lam_star, max_comb ) # P_lambda* at line 13
		k = fre_pattern.getTotal( lam_star )
	except frequentPatterns.LCMError, e:
		sys.exit()

	# multiple test by using k and lambda_star
	sys.stderr.write("finish calculation of K: %s\n" % k)
	# If lam_star > max_lambda, m_lambda set to max_lambda.
	# This case cause when optimal solution is found at first step.
	sys.stderr.write("%s\n" % lam_star)
	if (lam_star > max_lambda):
		lam_star = max_lambda
		
	correction_term_time = time.clock()
	return (fre_pattern, lam_star, max_lambda, correction_term_time, func_f)

# list up the combinations p_i <= alpha/k
def fwerControll(transaction_list, fre_pattern, lam_star, max_lambda, threshold, lcm2transaction_id, func_f, columnid2name):
	k = fre_pattern.getTotal( lam_star )
	enrich_lst = []
	i = 0
	max_itemset_size = 0 # the maximum itemset size in detection of our method. This value is used for Bonferroni correction.
 	for l in reversed( xrange( lam_star, max_lambda + 1 )):
		item_trans_list = fre_pattern.getFrequentList( l )
		for item_set_and_size in item_trans_list:
			i = i + 1
			item_set = item_set_and_size[0]
			sys.stderr.write("--- testing " + str(i) + " : ")
			sys.stderr.write("%s" % item_set)
#			print item_set,
			flag_transaction_list = [] # transaction list which has all items in itemset.
			for t in item_set_and_size[1]:
#				print t,
#				print " " + str(lcm2transaction_id[t]) + ", ",
				flag_transaction_list.append(lcm2transaction_id[t])
#			print " ---"
			p, stat_score = func_f.calPValue(transaction_list, flag_transaction_list)
			sys.stderr.write("p: " + str(p) + "\n")
			if p < (threshold/k):
				enrich_lst.append([item_set, p, len( item_set_and_size[1] ), stat_score])
				item_set_size = len(item_set)
				if ( item_set_size > max_itemset_size ):
					max_itemset_size = item_set_size
#			print "p: " + str(p)+ "  ",
#			print item_set

	finish_test_time = time.clock()
	
			
	sys.stdout.write("--- results ---\n")
	if (fre_pattern.getTotal( lam_star ) < 1):
		sys.stdout.write("Warning: there is no test which satisfying # target genes >= " + str(lam_star) + ".\n")
	sys.stdout.write("Threshold: " + str(threshold/k) + ", ")
	sys.stdout.write("Correction factor: " + str(k) + " (# of target genes >= " + str(lam_star) + ")\n" )
	sys.stdout.write("# of significance: " + str(len(enrich_lst)) + "\n")
	if len(enrich_lst) > 0:
		sys.stdout.write("Raw p-value\tAdjusted p-value\tCombination\t# of target genes\tStatistic score\n")
		enrich_lst.sort(lambda x,y:cmp(x[1], y[1]))
	for l in enrich_lst:
		sys.stdout.write(str(l[1]) + "\t" + str(k*l[1]) + "\t")
		out_column = ""
		for i in l[0]:
			out_column = out_column + columnid2name[i-1] + ","
		sys.stdout.write(out_column[:-1] + "\t" + str(l[2]) + "\t" + str(l[3]) + "\n")
		
	return (len(enrich_lst), finish_test_time) # return the number of enrich set for permutation
		
##
# Return max lambda. That is, max size itemset.
##
def maxLambda(transaction_list):
	# Count each item size
	item_sizes = {}
	for t in transaction_list:
		for item in t.itemset:
			# If item does not exist in item_size, then make mapping to 0
			if not item_sizes.has_key(item):
				item_sizes[item] = 0
			item_sizes[item] = item_sizes[item] + 1
	
	# Get max value in item_sizes
	max_value = 0
	for i in item_sizes.itervalues():
		if i > max_value:
			max_value = i
			
	return max_value

##
# Run multiple test.
# itemset_file: The file includes associations between TFs and genes.
#     Each line indicates a gene.
#     If gene is targeted by the TF, then value is 1, otherwise 0.
# flag_file: Each line indicates a gene. The column1 is gene name.
#     If gene has the feature, the column2 is 1. The other case 0.
# threshold: The statistical significance threshold.
# set_method: The procedure name for calibration p-value (fisher/u_test).
# max_comb: the maxmal size which the largest combination size in tests set.
# min_p_times: the integer whether permutation test (minP) is executed.
#     When the value is over than 0, the minP is run.
# fdr_flag: A flag to determine FWER or FDR control.
##
def run(transaction_file, flag_file, threshold, set_method, lcm_pass, max_comb):
	# read 2 files and get transaction list
	transaction_list = set()
	try:
		transaction_list, columnid2name, lcm2transaction_id = readFile.readFiles(transaction_file, flag_file)
		if (max_comb == None):
			max_comb = -1
	except ValueError, e:
		return
	except KeyError, e:
		return
	except readFile.ReadFileError, e:
		return
	
	# run multiple test
	transaction4lcm53 = transaction_file + ".4lcm53"
	# run 
	starttime = time.clock()
	fre_pattern, lam_star, max_lambda, correction_term_time, func_f \
				 = executeMultTest(transaction_list, transaction4lcm53, threshold, set_method, \
								   lcm_pass, max_comb)
	enrich_size, finish_test_time \
				 = fwerControll(transaction_list, fre_pattern, lam_star, max_lambda, \
								threshold, lcm2transaction_id, func_f, columnid2name)
	# output time cost
	sys.stdout.write("Time (sec.): Correction factor %s, P-value %s, Total %s\n" \
					 % (correction_term_time-starttime, finish_test_time - correction_term_time, finish_test_time-starttime))

if __name__ == "__main__":
	usage = "usage: %prog [options] transaction_file value_file significance_probability"
	p = OptionParser(usage = usage)
	p.add_option('-p', '--pvalue', dest = "pvalue_procedure", help = "Chose the p-value calculation procedure from 'fiehser' (Fisher's exact test), 'chi' (Chi-square test) or 'u_test' (Mann-Whitney's U-test)")

#	p.add_option('--lcm', dest = "lcm_pass", help = "Set LCM program pass if you do not have it the directory in multiple_test/lcm25/fim_closed")

	p.add_option('--max_comb', dest = "max_comb", help = "Set the maximum size of combination to be tested.")
	
	opts, args = p.parse_args()

	# check argsuments
	if len(args) != 3:
		sys.stderr.write("Error: input [target-file], [expression-file] and [significance-level].\n")
		sys.exit()
	max_comb = None
	if (not (opts.max_comb == None)):
		if (opts.max_comb.isdigit()):
			max_comb = int(opts.max_comb)
		else:
			sys.stderr.write("Error: max_comb must be an integer value.\n")
			sys.exit()
	opts.lcm_pass = None

	# check p-vlaue procedure
	if not opts.pvalue_procedure in set_opts:
		sys.stderr.write("Error: Choose \"fisher\" or \"u_test\" by using -p option\n")
		sys.exit()

	
	# check the file exist.
	if not os.path.isfile(args[0]):
		sys.stderr.write("IOError: No such file: \'" + args[0] + "\'\n")
		sys.exit()
	if not os.path.isfile(args[1]):
		sys.stderr.write("IOError: No such file: \'" + args[1] + "\'\n")
		sys.exit()
	try:
		sig_pro = float(args[2])
	except ValueError:
		sys.stderr.write("ArgumentsError: significance probabiliy must be an float value from 0.0 to 1.0.\n")
		sys.exit()

	if (sig_pro < 0) or (sig_pro > 1):
		sys.stderr.write("ArgumentsError: significance probabiliy must be an float value from 0.0 to 1.0.\n")
		sys.exit()
	
	run(args[0], args[1], float(args[2]), opts.pvalue_procedure, opts.lcm_pass, max_comb)

