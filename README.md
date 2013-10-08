kba-scorer
==========

scoring tools for TREC KBA

```
  $ cd src 
  $ python -m  kba.scorer.ccr  ../../2013-kba-runs/ ../data/trec-kba-ccr-judgments-2013-07-08.before-and-after-cutoff.filter-run.txt   &> 2013-kba-runs.log &
```

preliminary score stats:

```
(1) max(F(avg(P), avg(R)))
(2) max(SU)
```


|vital-only|(1)       |(2)    |
|---------:|:---------|:------|
|max	   |0.338     | 0.286 |
|median	   |0.205     | 0.210 |
|mean	   |0.188     | 0.214 |
|min	   |0	      | 0.109 |

|vital+useful|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.670     |0.575 |
|median	   |0.440     |0.395 |
|mean	   |0.388     |0.395 |
|min	   |0	      |0.171 |


<img src="plots/TREC-KBA-2013-CCR-vital+useful-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-CCR-vital+useful-P-R-F-scatter-plot" style="width: 200px; height: 200px;"/>

foo

max		 0.102578656	0.333333333
median		 0.007291027	0.299056874
mean		 0.028102079	0.231309375
min		 0		0.011571099