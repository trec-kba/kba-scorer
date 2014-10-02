kba-scorer
==========

scoring tools for TREC KBA

scorer2
-------

To run the ssf scorer in scorer2:

```
  $ python -m kba.scorer2.ssf /path/to/truth-data.json /path/to/run-submissions-dir/ /path/to/stream-items-dir/ --metric [all|sokalsneath|cosine|dot] --max-lines n 2> log > scores.txt &
```

This command will score each runfile located in /path/to/run-submissions-dir/, using the truth data located in /path/to/truth-data.json, by accessing the stream items in /path/to/stream-items-dir/ to extract the slot-fills. The command takes a couple of arguments: --metric lets you select among \[all, sokalsneath, cosine, dot\], --max-lines n is optional and lets you only reads the first n lines from the runfiles. You will then find logging information in log, and your scores in scores.txt, in the current working directory. This command may take a long time, as it must reach into the stream items in /path/to/stream-items-dir/ in order to extract the slot-fills.

A runfile is evaluated by building a profile from its slot fills over time, and then comparing this profile with the profile generated from the truth data. Profiles are compared on a slot-by-slot basis. For each slot, we compare the token counts in that slot-fill with the token counts in the slot-fill in the truth data. The method of comparison between two slots is controlled by the --metric option. For example, if we use the dot metric, we compute the dot-product of the token counts for the two slot-fills. A larger score means a better overlap between the slot-fills.

scorer
------

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
|max	   |0.311     | 0.277 |
|median	   |0.174     | 0.255 |
|mean	   |0.166     | 0.137 |
|min	   |0	      | 0.129 |


The numbers above are computed using all of the entities, even those without positive judgments, which has the affect of depressing all scores proportionally.  For reference, the scores below are computed using --require-positives, which excludes those entities for which there are no positive judgments:

|vital-only (--require-positives)|(1)       |(2)    | 
|---------:|:---------|:------|
|max	   |0.360     | 0.321 |
|median	   |0.201     | 0.230 |
|mean	   |0.193     | 0.274 |
|min	   |0	      | 0.149 |

<img src="plots/TREC-KBA-2013-CCR-vital-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-CCR-vital-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />

The hardest part of CCR is distinguishing between documents that are merely "useful" during the creation of an initial entity profile and those special "vital" documents that would change an already up-to-date profile.  By combining vital+useful as the filtering, the task gets easier:

|vital+useful|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.659     |0.570 |
|median	   |0.406     |0.423 |
|mean	   |0.376     |0.425 |
|min	   |0	      |0.317 |

<img src="plots/TREC-KBA-2013-CCR-vital+useful-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-CCR-vital+useful-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />


For KBA 2013, we piloted a new task that requires systems to identify phrases in the text that can be used as new slot values in the entity profile, such as CauseOfDeath and FoundedBy.  The SSF scorer operates in four stages.  The first stage simply measures the ability of systems to identify the slot_type that a document substantiates.  The high-recall system in the scatter plot is a manual baseline system that used the CCR training data as input and asserted all of the slot_types for every entity that name matched in a document text.

|SSF-DOCS|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.100     |0.333 |
|median	   |0.005     |0.323 |
|mean	   |0.026     |0.242 |
|min	   |0	      |0.012 |

<img src="plots/TREC-KBA-2013-SSF-DOCS-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-DOCS-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />


The second of four stages in SSF diagostics considers *only* a run's true positives from the DOCS stage, and scores them for byte range overlap against the truth data.  The [heuristic for string overlap is implemented here](https://github.com/trec-kba/kba-scorer/blob/master/src/kba/scorer/ssf.py#L353).  The manual baseline system scored the highest by almost +20% because it presented the document's longest sentence containing the entity name as the slot fill for every slot type --- the length requirement in the heuristic linked above does not heavily penalize such long slot fills, and perhaps it should.

|SSF-OVERLAP|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.657     |0.663 |
|median	   |0.005     |0.334 |
|mean	   |0.101     |0.370 |
|min	   |0	      |0.333 |

<img src="plots/TREC-KBA-2013-SSF-OVERLAP-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-OVERLAP-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />

The third of four stages in SSF diagostics considers *only* a run's true postivies from the OVERLAP stage, and measures whether systems accurately resolved coreferent slot fills, i.e. asserted the same equivalence identifier for two slot fills that mean the same thing.  This is arguably the most difficult part of SSF.

|SSF-FILL|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.155     |0.335 |
|median	   |0.00005   |0.333 |
|mean	   |0.026     |0.333 |
|min	   |0	      |0.333 |

<img src="plots/TREC-KBA-2013-SSF-FILL-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-FILL-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />

The fourth of four stages in SSF diagnostics considers *only* a run's true postivies from the FILL stage, and measures whether a system accurately discovers the first evidence of a new slot fill, i.e. can reject non-novel information about the events that are changing the entity's profile.

|SSF-DATE_HOUR|(1)     |(2)   |
|---------:|:---------|:-----|
|max	   |0.682     |0.544 |
|median	   |0.021     |0.021 |
|mean	   |0.136     |0.113 |
|min	   |0	      |0     |

<img src="plots/TREC-KBA-2013-SSF-DATE_HOUR-P-R-F-scatter-plot.png?raw=true" alt="TREC-KBA-2013-SSF-DATE_HOUR-P-R-F-scatter-plot" style="width: 400px; height: 400px;" height="400px" width="400px" />
