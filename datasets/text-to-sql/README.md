# Text-to-SQL data

The text-to-SQL benchmark uses two benchmarks from the [BIRD team](https://bird-bench.github.io) at the
University of Hong Kong, and one small database written for this repository. The BIRD team's data is not
redistributed here: `./fetch.sh` downloads it into `downloads/`, which git ignores. The sets built from it
(`bird`, `bird-plain`, `lsb`, `fleet`) are also ignored.

| Set | Source | Licence | In this repository |
|-|-|-|-|
| `bird` | [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev) (500 questions over 11 databases), plus the rest of BIRD dev for a query history | CC BY-SA 4.0 | No. Downloaded by `fetch.sh` |
| `lsb` | [LiveSQLBench-Large v1](https://huggingface.co/datasets/birdsql/livesqlbench-large-v1), with about 1,000 columns per database | CC BY-SA 4.0 ([GitHub](https://github.com/bird-bench/livesqlbench)), CC BY 4.0 (Hugging Face card) | No. Tasks downloaded by `fetch.sh`, dumps and answer SQL by a person |
| `fleet` | Every `bird` and `lsb` database together | As above | No. Built from the two sets |
| `novel` | An invented pollination contractor's database, its documentation and 120 questions | Apache 2.0, as this repository | Yes, in `novel/` |

## What a person has to do

`fetch.sh` downloads BIRD Mini-Dev, BIRD dev and the public LiveSQLBench files. Two LiveSQLBench files need
a person:

1. **The PostgreSQL dumps:** Download `postgre_table_dumps_large.zip` from the Google Drive link in the
   [dataset card](https://huggingface.co/datasets/birdsql/livesqlbench-large-v1) and save it in
   `downloads/lsb-large/`.
2. **The answer SQL:** The BIRD team keeps LiveSQLBench's answer SQL and test cases private so that they stay
   out of model training data. Email them at bird.bench25@gmail.com, as the
   [LiveSQLBench README](https://github.com/bird-bench/livesqlbench) describes, and save the file they send
   (`livesqlbench_large_v1_gt_kg_testcases_<date>.jsonl`) in `downloads/lsb-large/`. Don't commit or share
   it, or anything built from it: `runs/` holds answer caches made from it and is ignored by git for that
   reason.

Without these two files you can still run the `novel` and `bird` scenarios.

## How the BIRD data is changed

- **bird:** Each table is renamed to a code such as `tb03_ptnt` and each column to one such as `c_brthdy`, in
  the style of an enterprise data dictionary, so that a model can't answer from memory of BIRD.
  `build/bird_cryptic.py` rewrites every answer query to the new names with sqlglot. It keeps a question only
  if the rewritten query returns exactly the original result: 493 of the 500 questions pass. BIRD's
  per-question evidence hints are not given to the agent.
- **lsb:** The databases are loaded as published. The tasks are the 332 SELECT tasks, in the users' own
  wording.
- **Results that depend on the date:** A few answer queries use the current date (BIRD questions 1031 and
  1156, and LiveSQLBench tasks `disaster_relief_5`, `solar_panel_2` and `virtual_idol_15`). Their answers
  change over time, so rebuild the answer cache (`verify_gold.py`) on the day you run.

## Citations

If you use these results, please cite the BIRD team's work:

```bibtex
@article{li2024can,
  title={Can LLM Already Serve as a Database Interface? A Big Bench for Large-Scale Database Grounded Text-to-SQLs},
  author={Li, Jinyang and Hui, Binyuan and Qu, Ge and Yang, Jiaxi and Li, Binhua and Li, Bowen and Wang, Bailin and
          Qin, Bowen and Geng, Ruiying and Huo, Nan and others},
  journal={Advances in Neural Information Processing Systems},
  volume={36},
  year={2024}
}

@misc{livesqlbench2025,
  author       = {BIRD Team},
  title        = {LiveSQLBench: A Dynamic and Contamination-Free Benchmark for Evaluating LLMs on Real-World Text-to-SQL Tasks},
  year         = {2024},
  howpublished = {https://github.com/bird-bench/livesqlbench}
}
```
