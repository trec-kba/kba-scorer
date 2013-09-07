kba-scorer
==========

scoring tools for TREC KBA

  $ cd src 
  $ python -m  kba.scorer.ccr  ../../2013-kba-runs/ ../data/trec-kba-ccr-judgments-2013-07-08.before-and-after-cutoff.filter-run.txt   &> 2013-kba-runs.log &

preliminary score stats:

(1) max(avg(F))
(2) max(F(avg(P), avg(R)))
(3) max(SU)


vital-only
            (1)         (2)     (3)
max	    0.267	0.305	4.235
median	    0.152	0.190	0.226
mean	    0.136	0.172	0.283
min	    0		0	0.108


vital+useful
max	    0.785	0.850	13.7
mean	    0.302	0.349	0.573
median	    0.302	0.366	0.363
min	    0		0	0.171
