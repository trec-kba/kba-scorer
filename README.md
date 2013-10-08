kba-scorer
==========

scoring tools for TREC KBA

```
  $ cd src 
  $ python -m  kba.scorer.ccr --include-useful --cutoff-step 1 ../../2013-kba-runs/ ../data/trec-kba-ccr-judgments-2013-09-26-expanded-with-ssf-inferred-vitals-plus-len-clean_visible.before-and-after-cutoff.filter-run.txt >& 2013-kba-runs-ccr-include-useful.log &
  $ python -m  kba.scorer.ssf --pooled-only    --cutoff-step 1 ../../2013-kba-runs/ ../data/trec-kba-ssf-target-events-2013-07-16-expanded-stream-ids.json &> 2013-kba-runs-ssf-pooled-only.log &
```

preliminary score stats:

```
(1) max(F(avg(P), avg(R)))
(2) max(SU)
```

The primary evaluation metric is for "vital" documents in the [Cumulative Citation Recommendation (CCR) task](http://trec-kba.org/trec-kba-2013.shtml).  This score is computed for *all* runs, including SSF runs, which provide all of the input fields needed for CCR.

|vital-only|(1)       |(2)    | 
|---------:|:---------|:------|
|max	   |0.338     | 0.286 |
|median	   |0.205     | 0.210 |
|mean	   |0.188     | 0.214 |
|min	   |0	      | 0.109 |

<img src="plots/TREC-KBA-2013-CCR-vital-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-CCR-vital-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />

The hardest part of CCR is distinguishing between documents that are merely "useful" during the creation of an initial entity profile and those special "vital" documents that would change an already up-to-date profile.  By combining vital+useful as the filtering, the task gets easier:

|vital+useful|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.670     |0.575 |
|median	   |0.440     |0.395 |
|mean	   |0.388     |0.395 |
|min	   |0	      |0.171 |

<img src="plots/TREC-KBA-2013-CCR-vital+useful-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-CCR-vital+useful-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />


For KBA 2013, we piloted a new task that requires systems to identify phrases in the text that can be used as new slot values in the entity profile, such as CauseOfDeath and FoundedBy.  The SSF scorer operates in four stages.  The first stage simply measures the ability of systems to identify the slot_type that a document substantiates.  The high-recall system in the scatter plot is a manual baseline system that used the CCR training data as input and asserted all of the slot_types for every entity that name matched in a document text.

|SSF-DOCS|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.103     |0.333 |
|median	   |0.007     |0.299 |
|mean	   |0.028     |0.231 |
|min	   |0	      |0.012 |

<img src="plots/TREC-KBA-2013-SSF-DOCS-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-DOCS-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />


The second of four stages in SSF diagostics considers *only* a run's true positives from the DOCS stage, and scores them for byte range overlap against the truth data.  The [heuristic for string overlap is implemented here](https://github.com/trec-kba/kba-scorer/blob/master/src/kba/scorer/ssf.py#L353).  The manual baseline system scored the highest by almost +20% because it presented the document's longest sentence containing the entity name as the slot fill for every slot type --- the length requirement in the heuristic linked above does not heavily penalize such long slot fills, and perhaps it should.

|SSF-OVERLAP|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.672     |0.670 |
|median	   |0.095     |0.356 |
|mean	   |0.174     |0.299 |
|min	   |0	      |0     |

<img src="plots/TREC-KBA-2013-SSF-OVERLAP-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-OVERLAP-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />

The third of four stages in SSF diagostics considers *only* a run's true postivies from the OVERLAP stage, and measures whether systems accurately resolved coreferent slot fills, i.e. asserted the same equivalence identifier for two slot fills that mean the same thing.  This is arguably the most difficult part of SSF.

|SSF-FILL|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.159     |0.359 |
|median	   |0.0003    |0.311 |
|mean	   |0.036     |0.231 |
|min	   |0	      |0     |

<img src="plots/TREC-KBA-2013-SSF-FILL-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-FILL-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />

The fourth of four stages in SSF diagnostics considers *only* a run's true postivies from the FILL stage, and measures whether a system accurately discovers the first evidence of a new slot fill, i.e. can reject non-novel information about the events that are changing the entity's profile.

|SSF-DATE_HOUR|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.720     |0.711 |
|median	   |0.529     |0.469 |
|mean	   |0.408     |0.390 |
|min	   |0	      |0     |

<img src="plots/TREC-KBA-2013-SSF-DATE_HOUR-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-DATE_HOUR-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />
