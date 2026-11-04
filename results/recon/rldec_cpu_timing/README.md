CPU timing of RLDec on this machine (12 logical CPUs, no usable GPU), for the
time estimate in results/RUNS.md. Three training iterations per app
(the default is 20), run with

    ~/miniconda3/envs/rldec/bin/python -m java_pipeline.run_rldec --iterations 3 <app>

The outputs are smoke runs (labelled smoke in their JSON) and are not results.
Per-iteration times are read from the "finished training iteration" lines of
each run's logs.log, copied here as <app>.log.
